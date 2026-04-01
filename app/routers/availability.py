from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, datetime, timezone
from ..database import get_db
from ..models.availability import AvailabilityRequest
from ..models.dealer import Dealer
from ..schemas.availability import AvailabilityCreate, AvailabilityOut
from ..auth.jwt import get_current_admin

router = APIRouter()


def _to_out(r: AvailabilityRequest) -> AvailabilityOut:
    return AvailabilityOut(
        id=r.id, dealerId=r.dealer_id,
        weekStart=r.week_start.isoformat(),
        shift=r.shift,
        preferredDaysOff=r.preferred_days_off or [],
        submittedAt=r.submitted_at,
    )


@router.get("")
def list_availability(
    dealer_id: str | None = None,
    week_start: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(AvailabilityRequest)
    if dealer_id:
        q = q.filter(AvailabilityRequest.dealer_id == dealer_id)
    if week_start:
        q = q.filter(AvailabilityRequest.week_start == date.fromisoformat(week_start))
    return [_to_out(r) for r in q.order_by(AvailabilityRequest.submitted_at.desc()).all()]


@router.post("", status_code=201)
def create_availability(req: AvailabilityCreate, db: Session = Depends(get_db)):
    d = db.query(Dealer).filter(Dealer.id == req.dealerId).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dealer not found")
    ws = date.fromisoformat(req.weekStart)
    existing = db.query(AvailabilityRequest).filter(
        AvailabilityRequest.dealer_id == req.dealerId,
        AvailabilityRequest.week_start == ws,
    ).first()
    if existing:
        existing.shift = req.shift
        existing.preferred_days_off = req.preferredDaysOff
        existing.submitted_at = datetime.now(timezone.utc)
        db.commit()
        return {"id": existing.id}
    r = AvailabilityRequest(
        dealer_id=req.dealerId, week_start=ws,
        shift=req.shift, preferred_days_off=req.preferredDaysOff,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id}


@router.delete("/{avail_id}")
def delete_availability(avail_id: int, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    r = db.query(AvailabilityRequest).filter(AvailabilityRequest.id == avail_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(r)
    db.commit()
    return {"message": "Deleted"}
