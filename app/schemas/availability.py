from pydantic import BaseModel
from datetime import datetime


class AvailabilityCreate(BaseModel):
    eeNumber: str
    weekStart: str  # YYYY-MM-DD
    shift: str  # day | swing | night | mixed
    preferredDaysOff: list[int] = []


class AvailabilityOut(BaseModel):
    id: int
    dealerId: str
    weekStart: str
    shift: str
    preferredDaysOff: list[int]
    submittedAt: datetime

    class Config:
        from_attributes = True
