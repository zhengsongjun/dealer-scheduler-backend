from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date, timedelta
from ..database import get_db
from ..models.dealer import Dealer
from ..models.schedule import Schedule, ScheduleEntry
from ..models.time_off import TimeOffRequest
from ..models.ride_share import RideShareRequest
from ..models.availability import AvailabilityRequest
from ..schemas.dealer import DealerCreate, DealerUpdate, DealerOut, UserLoginRequest
from sqlalchemy import func as sa_func
from ..auth.jwt import get_current_admin

router = APIRouter()


def _to_out(d: Dealer) -> DealerOut:
    return DealerOut(
        id=d.id, eeNumber=d.ee_number, firstName=d.first_name, lastName=d.last_name,
        type=d.type, employment=d.employment, preferredShift=d.preferred_shift,
        daysOff=d.days_off or [], phone=d.phone, email=d.email,
        isActive=d.is_active, createdAt=d.created_at, updatedAt=d.updated_at,
    )


@router.get("")
def list_dealers(
    type: str | None = None,
    employment: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    q = db.query(Dealer).filter(Dealer.is_active == True)
    if type:
        q = q.filter(Dealer.type == type)
    if employment:
        q = q.filter(Dealer.employment == employment)
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            (Dealer.id.ilike(pattern)) |
            (Dealer.first_name.ilike(pattern)) |
            (Dealer.last_name.ilike(pattern))
        )
    total = q.count()
    dealers = q.order_by(Dealer.id).offset((page - 1) * size).limit(size).all()
    return {"total": total, "page": page, "size": size, "data": [_to_out(d) for d in dealers]}


@router.get("/by-ee/{ee_number}")
def get_dealer_by_ee(ee_number: str, db: Session = Depends(get_db)):
    d = db.query(Dealer).filter(Dealer.ee_number == ee_number).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dealer not found")
    return _to_out(d)


@router.post("/user-login")
def user_login(req: UserLoginRequest, db: Session = Depends(get_db)):
    d = db.query(Dealer).filter(Dealer.ee_number == req.eeNumber).first()
    if d:
        fn_match = d.first_name.lower() == req.firstName.strip().lower()
        ln_match = d.last_name.lower() == req.lastName.strip().lower()
        if fn_match or ln_match:
            return _to_out(d)
    # No match or not found — create new dealer
    max_id = db.query(sa_func.max(Dealer.id)).scalar()
    new_id = str(int(max_id) + 1) if max_id else "100001"
    new_dealer = Dealer(
        id=new_id,
        ee_number=req.eeNumber,
        first_name=req.firstName.strip(),
        last_name=req.lastName.strip(),
        type="tournament",
        employment="full_time",
        preferred_shift="flexible",
        days_off=[],
    )
    db.add(new_dealer)
    db.commit()
    db.refresh(new_dealer)
    return _to_out(new_dealer)


@router.get("/{dealer_id}")
def get_dealer(dealer_id: str, db: Session = Depends(get_db)):
    d = db.query(Dealer).filter(Dealer.id == dealer_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dealer not found")
    return _to_out(d)


@router.post("", status_code=201)
def create_dealer(req: DealerCreate, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    if db.query(Dealer).filter(Dealer.id == req.id).first():
        raise HTTPException(status_code=409, detail="Dealer ID already exists")
    d = Dealer(
        id=req.id, first_name=req.firstName, last_name=req.lastName,
        type=req.type, employment=req.employment, preferred_shift=req.preferredShift,
        days_off=req.daysOff, phone=req.phone, email=req.email,
    )
    db.add(d)
    db.commit()
    return {"id": d.id, "message": "Dealer created"}


@router.put("/{dealer_id}")
def update_dealer(dealer_id: str, req: DealerUpdate, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    d = db.query(Dealer).filter(Dealer.id == dealer_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dealer not found")
    for field, col in [
        ("firstName", "first_name"), ("lastName", "last_name"),
        ("type", "type"), ("employment", "employment"),
        ("preferredShift", "preferred_shift"), ("daysOff", "days_off"),
        ("phone", "phone"), ("email", "email"),
    ]:
        val = getattr(req, field)
        if val is not None:
            setattr(d, col, val)
    db.commit()
    return {"id": d.id, "message": "Dealer updated"}


@router.delete("/{dealer_id}")
def delete_dealer(dealer_id: str, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    d = db.query(Dealer).filter(Dealer.id == dealer_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dealer not found")
    d.is_active = False
    db.commit()
    return {"id": d.id, "message": "Dealer deactivated"}


# === User-side data query endpoints (by ee_number, no auth required) ===

def _get_dealer_by_ee(ee_number: str, db: Session) -> Dealer:
    d = db.query(Dealer).filter(Dealer.ee_number == ee_number).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dealer not found")
    return d


@router.get("/ee/{ee_number}/schedule")
def get_dealer_schedule(ee_number: str, week_start: str | None = None, db: Session = Depends(get_db)):
    d = _get_dealer_by_ee(ee_number, db)
    q = db.query(Schedule)
    if week_start:
        q = q.filter(Schedule.week_start == date.fromisoformat(week_start))
    schedules = q.order_by(Schedule.week_start.desc()).all()

    all_toffs = db.query(TimeOffRequest).filter(
        TimeOffRequest.dealer_id == d.id,
        TimeOffRequest.status == "approved",
    ).all()

    weeks = []
    for s in schedules:
        entries = []
        for e in db.query(ScheduleEntry).filter(
            ScheduleEntry.schedule_id == s.id, ScheduleEntry.dealer_id == d.id
        ).all():
            entries.append({"date": e.date.isoformat(), "shift": e.shift})
        ws = s.week_start
        we = ws + timedelta(days=6)
        time_off_dates = []
        for t in all_toffs:
            if t.start_date <= we and t.end_date >= ws:
                cur = max(t.start_date, ws)
                end = min(t.end_date, we)
                while cur <= end:
                    time_off_dates.append(cur.isoformat())
                    cur += timedelta(days=1)
        weeks.append({
            "weekStart": ws.isoformat(),
            "entries": entries,
            "timeOff": time_off_dates,
            "daysOff": d.days_off or [],
        })

    if week_start:
        w = weeks[0] if weeks else {"weekStart": week_start, "entries": [], "timeOff": [], "daysOff": d.days_off or []}
        return {"eeNumber": ee_number, **w}

    return {"eeNumber": ee_number, "weeks": weeks}


@router.get("/ee/{ee_number}/time-off")
def get_dealer_time_off(ee_number: str, db: Session = Depends(get_db)):
    d = _get_dealer_by_ee(ee_number, db)
    reqs = db.query(TimeOffRequest).filter(
        TimeOffRequest.dealer_id == d.id
    ).order_by(TimeOffRequest.submitted_at.desc()).all()
    return [{
        "id": r.id, "startDate": r.start_date.isoformat(),
        "endDate": r.end_date.isoformat(), "reason": r.reason,
        "status": r.status, "submittedAt": r.submitted_at.isoformat(),
    } for r in reqs]


@router.get("/ee/{ee_number}/ride-share")
def get_dealer_ride_share(ee_number: str, week_start: str | None = None, db: Session = Depends(get_db)):
    d = _get_dealer_by_ee(ee_number, db)
    reqs = db.query(RideShareRequest).filter(
        RideShareRequest.dealer_id == d.id, RideShareRequest.is_active == True
    )
    if week_start:
        reqs = reqs.filter(RideShareRequest.week_start == date.fromisoformat(week_start))
    reqs = reqs.order_by(RideShareRequest.created_at.desc()).all()
    return [{
        "id": r.id, "partnerName": r.partner_name,
        "partnerEENumber": r.partner_ee_number,
        "weekStart": r.week_start.isoformat() if r.week_start else None,
        "createdAt": r.created_at.isoformat(),
    } for r in reqs]


@router.get("/ee/{ee_number}/availability")
def get_dealer_availability(ee_number: str, week_start: str | None = None, db: Session = Depends(get_db)):
    d = _get_dealer_by_ee(ee_number, db)
    q = db.query(AvailabilityRequest).filter(AvailabilityRequest.dealer_id == d.id)
    if week_start:
        q = q.filter(AvailabilityRequest.week_start == date.fromisoformat(week_start))
    reqs = q.order_by(AvailabilityRequest.submitted_at.desc()).all()
    return [{
        "id": r.id, "weekStart": r.week_start.isoformat(),
        "shift": r.shift, "preferredDaysOff": r.preferred_days_off or [],
        "submittedAt": r.submitted_at.isoformat(),
    } for r in reqs]
