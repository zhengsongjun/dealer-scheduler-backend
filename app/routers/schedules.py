from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date, datetime, timezone, timedelta
from ..database import get_db
from ..models.schedule import Schedule, ScheduleEntry
from ..models.dealer import Dealer
from ..models.projection import Projection
from ..models.time_off import TimeOffRequest
from ..models.availability import AvailabilityRequest
from ..models.ride_share import RideShareRequest
from ..schemas.schedule import ScheduleGenerate, ScheduleOut, ScheduleEntryOut, GenerateResult
from ..services.scheduler import solve, DealerInfo, SlotDemand, RideShareGroup, SchedulerWeights
from ..models.scheduler_config import SchedulerConfig
from ..auth.jwt import get_current_admin

router = APIRouter()


@router.post("/generate")
def generate_schedule(req: ScheduleGenerate, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    ws = date.fromisoformat(req.weekStart)
    week_dates = [ws + timedelta(days=i) for i in range(7)]

    # 1. Load projection
    proj = db.query(Projection).filter(Projection.week_start == ws).first()
    if not proj:
        raise HTTPException(status_code=400, detail="No projection found for this week")

    # 2. Parse demands from projection data (aggregate same date+shift)
    demand_agg: dict[tuple[date, str], int] = {}
    for day_data in proj.data:
        d = date.fromisoformat(day_data["date"])
        for slot in day_data.get("slots", []):
            time_str = slot["time"].upper().strip()
            if "9" in time_str or "10" in time_str or "11" in time_str or "12" in time_str:
                shift = "9AM"
            else:
                shift = "4PM"
            key = (d, shift)
            demand_agg[key] = demand_agg.get(key, 0) + slot["dealersNeeded"]
    demands: list[SlotDemand] = [
        SlotDemand(date=k[0], shift=k[1], dealers_needed=v) for k, v in demand_agg.items()
    ]

    # 3. Load dealers
    db_dealers = db.query(Dealer).filter(
        Dealer.type == req.dealerType, Dealer.is_active == True
    ).all()
    if not db_dealers:
        raise HTTPException(status_code=400, detail="No active dealers of this type")

    # 4. Load approved time-off
    we = ws + timedelta(days=6)
    time_offs = db.query(TimeOffRequest).filter(
        TimeOffRequest.status == "approved",
        TimeOffRequest.start_date <= we,
        TimeOffRequest.end_date >= ws,
    ).all()
    time_off_map: dict[str, list[date]] = {}
    for to in time_offs:
        cur = max(to.start_date, ws)
        end = min(to.end_date, we)
        while cur <= end:
            time_off_map.setdefault(to.dealer_id, []).append(cur)
            cur += timedelta(days=1)

    # 5. Load availability submissions
    avails = db.query(AvailabilityRequest).filter(
        AvailabilityRequest.week_start == ws
    ).all()
    avail_map = {a.dealer_id: a for a in avails}

    # 6. Load ride share groups (group by dealer_id)
    ride_shares = db.query(RideShareRequest).filter(
        RideShareRequest.is_active == True
    ).all()
    rs_groups_raw: dict[str, list[str]] = {}
    for rs in ride_shares:
        rs_groups_raw.setdefault(rs.dealer_id, [])
        if rs.partner_ee_number:
            rs_groups_raw[rs.dealer_id].append(rs.partner_ee_number)
    ride_share_groups = []
    for did, partners in rs_groups_raw.items():
        members = [did] + [p for p in partners if p in {d.id for d in db_dealers}]
        if len(members) >= 2:
            ride_share_groups.append(RideShareGroup(group_key=did, member_ids=members))

    # 7. Build DealerInfo list
    dealer_infos = []
    for d in db_dealers:
        avail = avail_map.get(d.id)
        dealer_infos.append(DealerInfo(
            id=d.id,
            employment=d.employment,
            days_off=d.days_off or [],
            preferred_shift=d.preferred_shift or "flexible",
            availability_shift=avail.shift if avail else None,
            preferred_days_off=(avail.preferred_days_off or []) if avail else [],
            approved_time_off=time_off_map.get(d.id, []),
            ee_number=d.ee_number,
        ))

    # 8. Load scheduler weights from DB
    config_rows = db.query(SchedulerConfig).all()
    weight_map = {r.key: r.value for r in config_rows}
    weights = SchedulerWeights(**{k: weight_map[k] for k in weight_map if hasattr(SchedulerWeights, k)})

    # 9. Solve
    result = solve(dealer_infos, demands, ride_share_groups, ws, weights=weights)

    # 9. Save to DB
    existing = db.query(Schedule).filter(
        Schedule.week_start == ws, Schedule.dealer_type == req.dealerType
    ).first()
    if existing:
        db.query(ScheduleEntry).filter(ScheduleEntry.schedule_id == existing.id).delete()
        existing.generated_at = datetime.now(timezone.utc)
        existing.status = "draft"
        existing.published_at = None
        db.flush()
        schedule = existing
    else:
        schedule = Schedule(week_start=ws, dealer_type=req.dealerType)
        db.add(schedule)
        db.flush()

    for dealer_id, assign_date, shift in result.assignments:
        entry = ScheduleEntry(
            schedule_id=schedule.id,
            dealer_id=dealer_id,
            date=assign_date,
            shift=shift,
        )
        db.add(entry)
    db.commit()

    return GenerateResult(
        scheduleId=schedule.id,
        totalAssignments=result.total_assignments,
        unfilledSlots=result.unfilled_slots,
        solverStatus=result.solver_status,
        solveTimeMs=result.solve_time_ms,
    )


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
