from sqlalchemy import String, Integer, Boolean, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from ..database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(30), default="info")  # info | success | warning | error
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # optional link to related schedule
    schedule_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
