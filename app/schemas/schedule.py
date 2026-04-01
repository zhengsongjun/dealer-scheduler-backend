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
