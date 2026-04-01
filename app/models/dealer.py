from sqlalchemy import String, Boolean, Integer, Date, ARRAY, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import date, datetime
from ..database import Base


class Dealer(Base):
    __tablename__ = "dealers"

    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    ee_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50))
    type: Mapped[str] = mapped_column(String(20))  # tournament | cash | restart
    employment: Mapped[str] = mapped_column(String(20))  # full_time | part_time
    preferred_shift: Mapped[str] = mapped_column(String(20), default="flexible")
    days_off: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=[])
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(100), nullable=True)
    seniority_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
