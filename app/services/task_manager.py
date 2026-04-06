"""Database-backed task manager for async schedule generation."""
import json
import uuid
import logging
from datetime import datetime, timedelta, timezone

from ..database import SessionLocal
from ..models.task import TaskRecord

logger = logging.getLogger(__name__)


def _cleanup_old_tasks(db, max_age_hours: int = 24):
    """Delete completed/failed tasks older than max_age_hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    db.query(TaskRecord).filter(
        TaskRecord.status.in_(["completed", "failed"]),
        TaskRecord.created_at < cutoff,
    ).delete(synchronize_session=False)


def create_task() -> str:
    task_id = uuid.uuid4().hex[:12]
    db = SessionLocal()
    try:
        _cleanup_old_tasks(db)
        db.add(TaskRecord(id=task_id, status="pending", progress=0, phase=""))
        db.commit()
    finally:
        db.close()
    return task_id


def update_task(task_id: str, *, status: str | None = None,
                progress: int | None = None, phase: str | None = None,
                result: dict | None = None, error: str | None = None):
    db = SessionLocal()
    try:
        t = db.query(TaskRecord).filter(TaskRecord.id == task_id).first()
        if not t:
            return
        if status is not None:
            t.status = status
        if progress is not None:
            t.progress = progress
        if phase is not None:
            t.phase = phase
        if result is not None:
            t.result_json = json.dumps(result)
        if error is not None:
            t.error = error
        db.commit()
    finally:
        db.close()


def get_task(task_id: str) -> dict | None:
    db = SessionLocal()
    try:
        t = db.query(TaskRecord).filter(TaskRecord.id == task_id).first()
        if not t:
            return None
        return {
            "task_id": t.id,
            "status": t.status,
            "progress": t.progress,
            "phase": t.phase,
            "result": json.loads(t.result_json) if t.result_json else None,
            "error": t.error,
        }
    finally:
        db.close()
