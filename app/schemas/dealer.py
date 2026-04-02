from pydantic import BaseModel
from datetime import datetime


class UserLoginRequest(BaseModel):
    firstName: str
    lastName: str
    eeNumber: str


class DealerCreate(BaseModel):
    id: str
    firstName: str
    lastName: str
    type: str  # tournament | cash | restart
    employment: str  # full_time | part_time
    preferredShift: str = "flexible"
    daysOff: list[int] = []
    phone: str | None = None
    email: str | None = None


class DealerUpdate(BaseModel):
    firstName: str | None = None
    lastName: str | None = None
    type: str | None = None
    employment: str | None = None
    preferredShift: str | None = None
    daysOff: list[int] | None = None
    phone: str | None = None
    email: str | None = None


class DealerOut(BaseModel):
    id: str
    eeNumber: str | None
    firstName: str
    lastName: str
    type: str
    employment: str
    preferredShift: str
    daysOff: list[int]
    phone: str | None
    email: str | None
    isActive: bool
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True
