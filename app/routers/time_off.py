from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from ..database import get_db
from ..models.time_off import TimeOffRequest
from ..models.dealer import Dealer
from ..schemas.time_off import TimeOffCreate, TimeOffOut
from ..auth.jwt import get_current_admin

router = APIRouter()


def _to_out(r: TimeOffRequest) -> TimeOffOut:
    return TimeOffOut(
        id=r.id, dealerId=r.dealer_id,
        startDate=r.start_date.isoformat(), endDate=r.end_date.isoformat(),
        reason=r.reason, status=r.status,
        submittedAt=r.submitted_at, reviewedAt=r.reviewed_at,
    )


def _next_id(db: Session) -> str:
    last = db.query(TimeOffRequest).order_by(TimeOffRequest.id.desc()).first()
    if not last:
        return "TO0001"
    num = int(last.id[2:]) + 1
    return f"TO{num:04d}"


@router.get("")
def list_time_off(
    week_start: str | None = None,
    dealer_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(TimeOffRequest)
    if dealer_id:
        q = q.filter(TimeOffRequest.dealer_id == dealer_id)
    if status:
        q = q.filter(TimeOffRequest.status == status)
    if week_start:
        from datetime import date, timedelta
        ws = date.fromisoformat(week_start)
        we = ws + timedelta(days=6)
        q = q.filter(TimeOffRequest.start_date <= we, TimeOffRequest.end_date >= ws)
    return [_to_out(r) for r in q.order_by(TimeOffRequest.submitted_at.desc()).all()]


@router.post("", status_code=201)
def create_time_off(req: TimeOffCreate, db: Session = Depends(get_db)):
    from datetime import date
    d = db.query(Dealer).filter(Dealer.id == req.dealerId).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dealer not found")
    new_id = _next_id(db)
    r = TimeOffRequest(
        id=new_id, dealer_id=req.dealerId,
        start_date=date.fromisoformat(req.startDate),
        end_date=date.fromisoformat(req.endDate),
        reason=req.reason,
    )
    db.add(r)
    db.commit()
    return {"id": new_id, "status": "pending"}


@router.put("/{request_id}/approve")
def approve_time_off(request_id: str, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    r = db.query(TimeOffRequest).filter(TimeOffRequest.id == request_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    if r.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending requests can be approved")
    r.status = "approved"
    r.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": r.id, "status": "approved"}


@router.put("/{request_id}/reject")
def reject_time_off(request_id: str, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    r = db.query(TimeOffRequest).filter(TimeOffRequest.id == request_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    if r.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending requests can be rejected")
    r.status = "rejected"
    r.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": r.id, "status": "rejected"}


@router.delete("/{request_id}")
def delete_time_off(request_id: str, db: Session = Depends(get_db)):
    r = db.query(TimeOffRequest).filter(TimeOffRequest.id == request_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    if r.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending requests can be deleted")
    db.delete(r)
    db.commit()
    return {"message": "Deleted"}
