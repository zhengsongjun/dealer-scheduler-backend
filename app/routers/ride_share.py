from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.ride_share import RideShareRequest
from ..models.dealer import Dealer
from ..schemas.ride_share import RideShareCreate, RideShareOut
from ..auth.jwt import get_current_admin

router = APIRouter()


def _to_out(r: RideShareRequest) -> RideShareOut:
    return RideShareOut(
        id=r.id, dealerId=r.dealer_id,
        partnerName=r.partner_name, partnerEENumber=r.partner_ee_number,
        isActive=r.is_active, createdAt=r.created_at,
    )


def _next_id(db: Session) -> str:
    last = db.query(RideShareRequest).order_by(RideShareRequest.id.desc()).first()
    if not last:
        return "RS000001"
    num = int(last.id[2:]) + 1
    return f"RS{num:06d}"


@router.get("")
def list_ride_share(dealer_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(RideShareRequest).filter(RideShareRequest.is_active == True)
    if dealer_id:
        q = q.filter(RideShareRequest.dealer_id == dealer_id)
    return [_to_out(r) for r in q.order_by(RideShareRequest.created_at.desc()).all()]


@router.post("", status_code=201)
def create_ride_share(req: RideShareCreate, db: Session = Depends(get_db)):
    d = db.query(Dealer).filter(Dealer.id == req.dealerId).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dealer not found")
    ids = []
    for p in req.partners:
        rid = _next_id(db)
        r = RideShareRequest(
            id=rid, dealer_id=req.dealerId,
            partner_name=p.partnerName, partner_ee_number=p.partnerEENumber,
        )
        db.add(r)
        db.flush()
        ids.append(rid)
    db.commit()
    return {"ids": ids, "message": f"{len(ids)} ride share request(s) created"}


@router.put("/{request_id}/cancel")
def cancel_ride_share(request_id: str, db: Session = Depends(get_db)):
    r = db.query(RideShareRequest).filter(RideShareRequest.id == request_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    r.is_active = False
    db.commit()
    return {"id": r.id, "message": "Cancelled"}


@router.delete("/{request_id}")
def delete_ride_share(request_id: str, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    r = db.query(RideShareRequest).filter(RideShareRequest.id == request_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(r)
    db.commit()
    return {"message": "Deleted"}
