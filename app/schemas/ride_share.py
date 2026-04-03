from pydantic import BaseModel
from datetime import datetime, date


class RideSharePartner(BaseModel):
    partnerName: str
    partnerEENumber: str | None = None


class RideShareCreate(BaseModel):
    eeNumber: str
    weekStart: str
    partners: list[RideSharePartner]


class RideShareOut(BaseModel):
    id: str
    dealerId: str
    weekStart: date | None
    partnerName: str
    partnerEENumber: str | None
    isActive: bool
    createdAt: datetime

    class Config:
        from_attributes = True
