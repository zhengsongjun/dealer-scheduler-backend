from pydantic import BaseModel
from datetime import datetime


class RideSharePartner(BaseModel):
    partnerName: str
    partnerEENumber: str | None = None


class RideShareCreate(BaseModel):
    dealerId: str
    partners: list[RideSharePartner]


class RideShareOut(BaseModel):
    id: str
    dealerId: str
    partnerName: str
    partnerEENumber: str | None
    isActive: bool
    createdAt: datetime

    class Config:
        from_attributes = True
