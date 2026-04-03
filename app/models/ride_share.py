from sqlalchemy import String, Boolean, Date, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, date
from ..database import Base


class RideShareRequest(Base):
    __tablename__ = "ride_share_requests"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    dealer_id: Mapped[str] = mapped_column(String(10))
    week_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    partner_name: Mapped[str] = mapped_column(String(100))
    partner_ee_number: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
