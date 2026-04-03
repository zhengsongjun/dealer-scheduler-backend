from pydantic import BaseModel
from datetime import datetime


class TimeOffCreate(BaseModel):
    eeNumber: str
    startDate: str  # YYYY-MM-DD
    endDate: str
    reason: str | None = None


class TimeOffOut(BaseModel):
    id: str
    dealerId: str
    startDate: str
    endDate: str
    reason: str | None
    status: str
    submittedAt: datetime
    reviewedAt: datetime | None

    class Config:
        from_attributes = True
