from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import date, timedelta
from ..database import get_db
from ..models.time_off import TimeOffRequest
from ..models.availability import AvailabilityRequest
from ..models.ride_share import RideShareRequest
from ..models.dealer import Dealer
from ..auth.jwt import get_current_admin

router = APIRouter()

DAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']


@router.get("/summary")
def requests_summary(week_start: str | None = None, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    result = {"availability": {"total": 0}, "timeOff": {"pending": 0, "approved": 0, "rejected": 0}, "rideShare": {"active": 0}}
    if week_start:
        ws = date.fromisoformat(week_start)
        we = ws + timedelta(days=6)
        result["availability"]["total"] = db.query(AvailabilityRequest).filter(
            AvailabilityRequest.week_start == ws
        ).count()
        for s in ["pending", "approved", "rejected"]:
            result["timeOff"][s] = db.query(TimeOffRequest).filter(
                TimeOffRequest.status == s,
                TimeOffRequest.start_date <= we,
                TimeOffRequest.end_date >= ws,
            ).count()
        result["rideShare"]["active"] = db.query(RideShareRequest).filter(
            RideShareRequest.is_active == True,
            RideShareRequest.week_start == ws,
        ).count()
    return result


@router.get("/availability")
def requests_availability(week_start: str | None = None, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=10000), db: Session = Depends(get_db), _=Depends(get_current_admin)):
    q = db.query(AvailabilityRequest, Dealer).outerjoin(
        Dealer, Dealer.id == AvailabilityRequest.dealer_id
    )
    if week_start:
        q = q.filter(AvailabilityRequest.week_start == date.fromisoformat(week_start))
    q = q.order_by(AvailabilityRequest.submitted_at.desc())
    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    result = []
    for r, dealer in rows:
        name = f"{dealer.first_name} {dealer.last_name}" if dealer else r.dealer_id
        result.append({
            "id": r.id, "dealerId": r.dealer_id, "dealerName": name,
            "eeNumber": dealer.ee_number if dealer else None,
            "weekStart": r.week_start.isoformat(), "shift": r.shift,
            "preferredDaysOff": r.preferred_days_off or [],
            "submittedAt": r.submitted_at.isoformat(),
        })
    return {"data": result, "total": total}


@router.get("/time-off")
def requests_time_off(week_start: str | None = None, status: str | None = None, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db), _=Depends(get_current_admin)):
    q = db.query(TimeOffRequest, Dealer).outerjoin(
        Dealer, Dealer.id == TimeOffRequest.dealer_id
    )
    if week_start:
        ws = date.fromisoformat(week_start)
        we = ws + timedelta(days=6)
        q = q.filter(TimeOffRequest.start_date <= we, TimeOffRequest.end_date >= ws)
    if status:
        q = q.filter(TimeOffRequest.status == status)
    q = q.order_by(TimeOffRequest.submitted_at.desc())
    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    result = []
    for r, dealer in rows:
        name = f"{dealer.first_name} {dealer.last_name}" if dealer else r.dealer_id
        result.append({
            "id": r.id, "dealerId": r.dealer_id, "dealerName": name,
            "eeNumber": dealer.ee_number if dealer else None,
            "startDate": r.start_date.isoformat(), "endDate": r.end_date.isoformat(),
            "reason": r.reason, "status": r.status,
            "submittedAt": r.submitted_at.isoformat(),
        })
    return {"data": result, "total": total}


@router.get("/ride-share")
def requests_ride_share(week_start: str | None = None, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db), _=Depends(get_current_admin)):
    q = db.query(RideShareRequest, Dealer).outerjoin(
        Dealer, Dealer.id == RideShareRequest.dealer_id
    ).filter(
        RideShareRequest.is_active == True
    )
    if week_start:
        q = q.filter(RideShareRequest.week_start == date.fromisoformat(week_start))
    q = q.order_by(RideShareRequest.created_at.desc())
    rows = q.all()

    # Group by dealer_id + week_start
    from collections import OrderedDict
    groups: dict[tuple, dict] = OrderedDict()
    for r, dealer in rows:
        key = (r.dealer_id, r.week_start.isoformat() if r.week_start else None)
        if key not in groups:
            name = f"{dealer.first_name} {dealer.last_name}" if dealer else r.dealer_id
            groups[key] = {
                "dealerId": r.dealer_id, "dealerName": name,
                "eeNumber": dealer.ee_number if dealer else None,
                "weekStart": r.week_start.isoformat() if r.week_start else None,
                "createdAt": r.created_at.isoformat(),
                "partners": [],
            }
        groups[key]["partners"].append({
            "id": r.id,
            "partnerName": r.partner_name,
            "partnerEENumber": r.partner_ee_number,
        })

    all_groups = list(groups.values())
    total = len(all_groups)
    paginated = all_groups[(page - 1) * size: (page - 1) * size + size]
    return {"data": paginated, "total": total}
