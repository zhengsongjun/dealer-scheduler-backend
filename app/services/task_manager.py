"""In-memory task manager for async schedule generation."""
import threading
import uuid
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    LOADING = "loading"       # loading data from DB
    SOLVING = "solving"       # solver running
    SAVING = "saving"         # saving results to DB
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskInfo:
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0          # 0-100
    phase: str = ""            # human-readable phase description
    result: dict | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)


_tasks: dict[str, TaskInfo] = {}
_lock = threading.Lock()


def create_task() -> str:
    task_id = uuid.uuid4().hex[:12]
    with _lock:
        _tasks[task_id] = TaskInfo(task_id=task_id)
    return task_id


def update_task(task_id: str, *, status: TaskStatus | None = None,
                progress: int | None = None, phase: str | None = None,
                result: dict | None = None, error: str | None = None):
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return
        if status is not None:
            t.status = status
        if progress is not None:
            t.progress = progress
        if phase is not None:
            t.phase = phase
        if result is not None:
            t.result = result
        if error is not None:
            t.error = error


def get_task(task_id: str) -> TaskInfo | None:
    with _lock:
        return _tasks.get(task_id)


def cleanup_old_tasks(max_age_seconds: int = 3600):
    """Remove tasks older than max_age_seconds."""
    now = time.time()
    with _lock:
        to_remove = [k for k, v in _tasks.items() if now - v.created_at > max_age_seconds]
        for k in to_remove:
            del _tasks[k]
