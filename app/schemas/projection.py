from pydantic import BaseModel
from typing import Any


class ProjectionSlot(BaseModel):
    time: str
    dealersNeeded: int


class ProjectionDay(BaseModel):
    date: str
    slots: list[ProjectionSlot]


class ProjectionSave(BaseModel):
    days: list[ProjectionDay]


class ProjectionOut(BaseModel):
    weekStart: str
    days: list[ProjectionDay]
