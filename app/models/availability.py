from sqlalchemy import String, Integer, Date, ARRAY, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import date, datetime
from ..database import Base


class AvailabilityRequest(Base):
    __tablename__ = "availability_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dealer_id: Mapped[str] = mapped_column(String(10))
    week_start: Mapped[date] = mapped_column(Date)
    shift: Mapped[str] = mapped_column(String(20))  # day | swing | mixed
    preferred_days_off: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=[])
    submitted_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        # unique constraint: one submission per dealer per week
        {"comment": "UNIQUE (dealer_id, week_start) enforced via upsert logic"},
    )
