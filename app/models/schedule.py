from sqlalchemy import String, Integer, Date, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import date, datetime
from ..database import Base


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    week_start: Mapped[date] = mapped_column(Date)
    dealer_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | published
    generated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ScheduleEntry(Base):
    __tablename__ = "schedule_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(Integer, ForeignKey("schedules.id", ondelete="CASCADE"))
    dealer_id: Mapped[str] = mapped_column(String(10), ForeignKey("dealers.id"))
    date: Mapped[date] = mapped_column(Date)
    shift: Mapped[str] = mapped_column(String(10))  # 9AM | 4PM
