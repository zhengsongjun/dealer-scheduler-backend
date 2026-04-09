import re
import threading
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date, datetime, timezone, timedelta
from ..database import get_db, SessionLocal
from ..models.schedule import Schedule, ScheduleEntry
from ..models.dealer import Dealer
from ..models.projection import Projection
from ..models.time_off import TimeOffRequest
from ..models.availability import AvailabilityRequest
from ..models.ride_share import RideShareRequest
from ..models.notification import Notification
from ..schemas.schedule import ScheduleGenerate, ScheduleOut, ScheduleEntryOut, GenerateResult, TaskStartResult, TaskStatusOut
from ..services.scheduler import solve, DealerInfo, SlotDemand, RideShareGroup, SchedulerWeights
from ..services.task_manager import create_task, update_task, get_task
from ..models.scheduler_config import SchedulerConfig
from ..auth.jwt import get_current_admin

router = APIRouter()


def _time_to_shift(time_str: str) -> str:
    """Map a projection time slot string (e.g. '11 AM', '3 PM') to a shift.

    Rules:
      before 1 PM  -> 8AM  (day)
      1 PM - 5 PM  -> 4PM  (swing)
      6 PM+        -> 8PM  (night)
    """
    s = time_str.strip().upper()
    m = re.match(r"(\d{1,2})\s*(AM|PM)", s)
    if not m:
        return "8AM"  # fallback
    hour = int(m.group(1))
    ampm = m.group(2)
    # Convert to 24h
    if ampm == "AM":
        h24 = 0 if hour == 12 else hour
    else:
        h24 = hour if hour == 12 else hour + 12
    if h24 < 13:
        return "8AM"
    if h24 < 18:
        return "4PM"
    return "8PM"


@router.post("/generate")
def generate_schedule(req: ScheduleGenerate, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    ws = date.fromisoformat(req.weekStart)

    # Validate projection exists before starting background task
    proj = db.query(Projection).filter(Projection.week_start == ws).first()
    if not proj:
        raise HTTPException(status_code=400, detail="No projection found for this week")

    db_dealers = db.query(Dealer).filter(
        Dealer.type == req.dealerType, Dealer.is_active == True
    ).all()
    if not db_dealers:
        raise HTTPException(status_code=400, detail="No active dealers of this type")

    task_id = create_task()
    threading.Thread(
        target=_run_generate,
        args=(task_id, req.weekStart, req.dealerType),
        daemon=True,
    ).start()

    return TaskStartResult(taskId=task_id)


@router.get("/tasks/{task_id}")
def get_task_status(task_id: str):
    t = get_task(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    result = None
    if t["result"]:
        result = GenerateResult(**t["result"])
    return TaskStatusOut(
        taskId=t["task_id"], status=t["status"],
        progress=t["progress"], phase=t["phase"],
        result=result, error=t["error"],
    )


def _run_generate(task_id: str, week_start_str: str, dealer_type: str):
    """Background thread: load data, solve, save, create notification."""
    import logging
    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        ws = date.fromisoformat(week_start_str)
        we = ws + timedelta(days=6)

        # Phase 1: Loading data (0-20%)
        update_task(task_id, status="loading", progress=5, phase="Loading projection data")
        proj = db.query(Projection).filter(Projection.week_start == ws).first()
        demand_agg: dict[tuple[date, str], int] = {}
        for day_data in proj.data:
            d = date.fromisoformat(day_data["date"])
            for slot in day_data.get("slots", []):
                shift = _time_to_shift(slot["time"])
                key = (d, shift)
                demand_agg[key] = demand_agg.get(key, 0) + slot["dealersNeeded"]
        demands = [SlotDemand(date=k[0], shift=k[1], dealers_needed=v) for k, v in demand_agg.items()]

        update_task(task_id, progress=10, phase="Loading dealer data")
        db_dealers = db.query(Dealer).filter(Dealer.type == dealer_type, Dealer.is_active == True).all()

        time_offs = db.query(TimeOffRequest).filter(
            TimeOffRequest.status == "approved", TimeOffRequest.start_date <= we, TimeOffRequest.end_date >= ws,
        ).all()
        time_off_map: dict[str, list[date]] = {}
        for to in time_offs:
            cur = max(to.start_date, ws)
            end = min(to.end_date, we)
            while cur <= end:
                time_off_map.setdefault(to.dealer_id, []).append(cur)
                cur += timedelta(days=1)

        avails = db.query(AvailabilityRequest).filter(AvailabilityRequest.week_start == ws).all()
        avail_map = {a.dealer_id: a for a in avails}

        ride_shares = db.query(RideShareRequest).filter(
            RideShareRequest.is_active == True, RideShareRequest.week_start == ws,
        ).all()
        rs_groups_raw: dict[str, list[str]] = {}
        for rs in ride_shares:
            rs_groups_raw.setdefault(rs.dealer_id, [])
            if rs.partner_ee_number:
                rs_groups_raw[rs.dealer_id].append(rs.partner_ee_number)
        ee_to_id = {d.ee_number: d.id for d in db_dealers if d.ee_number}
        ride_share_groups = []
        for did, partner_ees in rs_groups_raw.items():
            member_ids = [did]
            for ee in partner_ees:
                pid = ee_to_id.get(ee)
                if pid:
                    member_ids.append(pid)
            if len(member_ids) >= 2:
                ride_share_groups.append(RideShareGroup(group_key=did, member_ids=member_ids))

        update_task(task_id, progress=15, phase="Building schedule model")
        dealer_infos = []
        for d in db_dealers:
            avail = avail_map.get(d.id)
            dealer_infos.append(DealerInfo(
                id=d.id, employment=d.employment, days_off=d.days_off or [],
                preferred_shift=d.preferred_shift or "flexible",
                availability_shift=avail.shift if avail else None,
                preferred_days_off=(avail.preferred_days_off or []) if avail else [],
                approved_time_off=time_off_map.get(d.id, []),
                ee_number=d.ee_number,
            ))

        config_rows = db.query(SchedulerConfig).all()
        weight_map = {r.key: r.value for r in config_rows}
        weights = SchedulerWeights(**{k: weight_map[k] for k in weight_map if hasattr(SchedulerWeights, k)})

        # Phase 2: Solving (20-85%)
        update_task(task_id, status="solving", progress=20, phase="Solver running")
        result = solve(dealer_infos, demands, ride_share_groups, ws, weights=weights)

        # Phase 3: Saving (85-95%)
        update_task(task_id, status="saving", progress=85, phase="Saving schedule")
        existing = db.query(Schedule).filter(Schedule.week_start == ws, Schedule.dealer_type == dealer_type).first()
        if existing:
            db.query(ScheduleEntry).filter(ScheduleEntry.schedule_id == existing.id).delete()
            existing.generated_at = datetime.now(timezone.utc)
            existing.status = "draft"
            existing.published_at = None
            db.flush()
            schedule = existing
        else:
            schedule = Schedule(week_start=ws, dealer_type=dealer_type)
            db.add(schedule)
            db.flush()

        for dealer_id, assign_date, shift in result.assignments:
            db.add(ScheduleEntry(schedule_id=schedule.id, dealer_id=dealer_id, date=assign_date, shift=shift))

        # Compute stats
        update_task(task_id, progress=90, phase="Computing statistics")
        stats = _compute_stats(dealer_infos, avail_map, result, demands)
        schedule.stats = stats

        db.commit()

        # Create notification
        update_task(task_id, progress=95, phase="Sending notification")
        _create_notification(db, schedule.id, result.solver_status, result.total_assignments, result.unfilled_slots, week_start_str)

        gen_result = dict(
            scheduleId=schedule.id, totalAssignments=result.total_assignments,
            unfilledSlots=result.unfilled_slots, solverStatus=result.solver_status,
            solveTimeMs=result.solve_time_ms, stats=stats,
        )
        update_task(task_id, status="completed", progress=100, phase="Completed", result=gen_result)

    except Exception as e:
        logger.exception("Schedule generation failed")
        update_task(task_id, status="failed", progress=0, phase="Failed", error=str(e))
    finally:
        db.close()


def _compute_stats(dealer_infos, avail_map, result, demands):
    """Compute satisfaction and unfilled slot stats."""
    SHIFT_MAP = {"8AM": "day", "4PM": "swing", "8PM": "night"}
    # Adjacent shifts within 2-hour float tolerance (no satisfaction penalty)
    SHIFT_HOURS = {"8AM": 8, "4PM": 16, "8PM": 20}
    FLOAT_HOURS = 2
    def _is_compatible(assigned_shift: str, pref_shift_name: str) -> bool:
        """Check if assigned shift matches or is adjacent to preferred shift."""
        if SHIFT_MAP.get(assigned_shift) == pref_shift_name:
            return True
        # Find the preferred shift code
        pref_code = next((k for k, v in SHIFT_MAP.items() if v == pref_shift_name), None)
        if not pref_code:
            return False
        return abs(SHIFT_HOURS.get(assigned_shift, 0) - SHIFT_HOURS.get(pref_code, 0)) <= FLOAT_HOURS

    # Build per-dealer assignment map
    dealer_assignments: dict[str, list[tuple[date, str]]] = {}
    for did, d, s in result.assignments:
        dealer_assignments.setdefault(did, []).append((d, s))

    fully_satisfied = 0
    partially_satisfied = 0
    unsatisfied = 0
    total_with_pref = 0

    for di in dealer_infos:
        avail = avail_map.get(di.id)
        if not avail:
            continue
        total_with_pref += 1
        assigns = dealer_assignments.get(di.id, [])
        if not assigns:
            unsatisfied += 1
            continue

        # Shift satisfaction (with float tolerance)
        shift_ok = True
        if avail.shift and avail.shift != "mixed":
            for _, s in assigns:
                if not _is_compatible(s, avail.shift):
                    shift_ok = False
                    break

        # Days off satisfaction
        pref_days = set(avail.preferred_days_off or [])
        days_off_ok = True
        if pref_days:
            assigned_weekdays = {d.weekday() for d, _ in assigns}
            # Convert JS weekday (0=Sun) to Python weekday (0=Mon)
            py_pref = set()
            mapping = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
            for pd in pref_days:
                py_pref.add(mapping.get(pd, pd))
            if py_pref & assigned_weekdays:
                days_off_ok = False

        if shift_ok and days_off_ok:
            fully_satisfied += 1
        elif shift_ok or days_off_ok:
            partially_satisfied += 1
        else:
            unsatisfied += 1

    # Unfilled slots breakdown
    assigned_count: dict[tuple[str, str], int] = {}
    for _, d, s in result.assignments:
        key = (d.isoformat(), s)
        assigned_count[key] = assigned_count.get(key, 0) + 1
    unfilled_breakdown = []
    for dm in demands:
        key = (dm.date.isoformat(), dm.shift)
        assigned = assigned_count.get(key, 0)
        if assigned < dm.dealers_needed:
            unfilled_breakdown.append({
                "date": dm.date.isoformat(), "shift": dm.shift,
                "needed": dm.dealers_needed, "assigned": assigned,
                "gap": dm.dealers_needed - assigned,
            })

    return {
        "fullySatisfied": fully_satisfied,
        "partiallySatisfied": partially_satisfied,
        "unsatisfied": unsatisfied,
        "totalWithPreference": total_with_pref,
        "unfilledBreakdown": unfilled_breakdown,
    }


def _create_notification(db, schedule_id, solver_status, total, unfilled, week_start_str):
    STATUS_LABELS = {
        "OPTIMAL": "Optimal", "CLOUD_OPTIMAL": "Optimal",
        "FEASIBLE": "Feasible", "CLOUD_FEASIBLE": "Feasible",
        "INFEASIBLE": "Failed", "CLOUD_INFEASIBLE": "Failed",
    }
    STATUS_TYPES = {
        "OPTIMAL": "success", "CLOUD_OPTIMAL": "success",
        "FEASIBLE": "warning", "CLOUD_FEASIBLE": "warning",
        "INFEASIBLE": "error", "CLOUD_INFEASIBLE": "error",
    }
    label = STATUS_LABELS.get(solver_status, "Unknown")
    ntype = STATUS_TYPES.get(solver_status, "info")
    msg = f"Week {week_start_str} schedule completed: {label}, {total} shifts"
    if unfilled > 0:
        msg += f", {unfilled} unfilled"
    notif = Notification(title=label, message=msg, type=ntype, schedule_id=schedule_id)
    db.add(notif)
    db.commit()


@router.delete("")
def clear_schedule(
    week_start: str,
    dealer_type: str = "tournament",
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    ws = date.fromisoformat(week_start)
    s = db.query(Schedule).filter(
        Schedule.week_start == ws, Schedule.dealer_type == dealer_type
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="No schedule found for this week")
    db.query(ScheduleEntry).filter(ScheduleEntry.schedule_id == s.id).delete()
    db.delete(s)
    db.commit()
    return {"message": "Schedule cleared"}


@router.get("")
def list_schedules(
    week_start: str | None = None,
    dealer_type: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Schedule)
    if week_start:
        q = q.filter(Schedule.week_start == date.fromisoformat(week_start))
    if dealer_type:
        q = q.filter(Schedule.dealer_type == dealer_type)
    schedules = q.order_by(Schedule.generated_at.desc()).all()
    result = []
    for s in schedules:
        entries = db.query(ScheduleEntry).filter(ScheduleEntry.schedule_id == s.id).all()
        result.append(ScheduleOut(
            id=s.id, weekStart=s.week_start.isoformat(),
            dealerType=s.dealer_type, status=s.status,
            entries=[ScheduleEntryOut(dealerId=e.dealer_id, date=e.date.isoformat(), shift=e.shift) for e in entries],
        ))
    return result


@router.get("/export")
def export_schedule(week_start: str, dealer_type: str = "tournament", db: Session = Depends(get_db)):
    from fastapi.responses import StreamingResponse
    from ..services.excel_export import export_schedule_excel
    ws = date.fromisoformat(week_start)
    s = db.query(Schedule).filter(
        Schedule.week_start == ws, Schedule.dealer_type == dealer_type
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found")
    output = export_schedule_excel(s.id, db)
    filename = f"schedule_{dealer_type}_{week_start}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{schedule_id}/entries")
def get_entries(schedule_id: int, db: Session = Depends(get_db)):
    s = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found")
    entries = db.query(ScheduleEntry).filter(ScheduleEntry.schedule_id == schedule_id).all()
    return [ScheduleEntryOut(dealerId=e.dealer_id, date=e.date.isoformat(), shift=e.shift) for e in entries]


@router.put("/{schedule_id}/publish")
def publish_schedule(schedule_id: int, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    s = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found")
    s.status = "published"
    s.published_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": s.id, "status": "published"}
