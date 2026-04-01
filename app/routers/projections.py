from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date
from ..database import get_db
from ..models.projection import Projection
from ..schemas.projection import ProjectionSave, ProjectionOut
from ..auth.jwt import get_current_admin

router = APIRouter()


@router.get("/{week_start}")
def get_projection(week_start: str, db: Session = Depends(get_db)):
    ws = date.fromisoformat(week_start)
    p = db.query(Projection).filter(Projection.week_start == ws).first()
    if not p:
        raise HTTPException(status_code=404, detail="Projection not found")
    return ProjectionOut(weekStart=p.week_start.isoformat(), days=p.data)


@router.put("/{week_start}")
def save_projection(week_start: str, req: ProjectionSave, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    ws = date.fromisoformat(week_start)
    p = db.query(Projection).filter(Projection.week_start == ws).first()
    data = [d.model_dump() for d in req.days]
    if p:
        p.data = data
    else:
        p = Projection(week_start=ws, data=data)
        db.add(p)
    db.commit()
    return {"weekStart": week_start, "message": "Projection saved"}
