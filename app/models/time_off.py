from sqlalchemy import String, Date, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import date, datetime
from ..database import Base


class TimeOffRequest(Base):
    __tablename__ = "time_off_requests"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    dealer_id: Mapped[str] = mapped_column(String(10))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | rejected
    submitted_at: Mapped[datetime] = mapped_column(server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
