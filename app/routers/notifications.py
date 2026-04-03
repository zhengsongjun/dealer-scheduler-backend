from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.notification import Notification

router = APIRouter()


@router.get("")
def list_notifications(db: Session = Depends(get_db)):
    rows = db.query(Notification).order_by(Notification.created_at.desc()).limit(50).all()
    return [_to_out(r) for r in rows]


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db)):
    count = db.query(Notification).filter(Notification.is_read == False).count()
    return {"count": count}


@router.put("/{nid}/read")
def mark_read(nid: int, db: Session = Depends(get_db)):
    n = db.query(Notification).filter(Notification.id == nid).first()
    if n:
        n.is_read = True
        db.commit()
    return {"ok": True}


@router.put("/read-all")
def mark_all_read(db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.is_read == False).update({"is_read": True})
    db.commit()
    return {"ok": True}


def _to_out(n: Notification):
    return {
        "id": n.id,
        "title": n.title,
        "message": n.message,
        "type": n.type,
        "isRead": n.is_read,
        "createdAt": n.created_at.isoformat() if n.created_at else None,
        "scheduleId": n.schedule_id,
    }
