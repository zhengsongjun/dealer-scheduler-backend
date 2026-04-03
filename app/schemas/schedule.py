from pydantic import BaseModel
from datetime import datetime


class ScheduleGenerate(BaseModel):
    weekStart: str
    dealerType: str = "tournament"


class ScheduleEntryOut(BaseModel):
    dealerId: str
    date: str
    shift: str


class ScheduleOut(BaseModel):
    id: int
    weekStart: str
    dealerType: str
    status: str
    entries: list[ScheduleEntryOut] = []


class GenerateResult(BaseModel):
    scheduleId: int
    totalAssignments: int
    unfilledSlots: int
    solverStatus: str
    solveTimeMs: int
    stats: dict | None = None


class TaskStartResult(BaseModel):
    taskId: str


class TaskStatusOut(BaseModel):
    taskId: str
    status: str
    progress: int
    phase: str
    result: GenerateResult | None = None
    error: str | None = None
