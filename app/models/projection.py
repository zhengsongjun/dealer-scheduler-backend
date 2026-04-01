from sqlalchemy import Integer, Date, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from datetime import date, datetime
from ..database import Base


class Projection(Base):
    __tablename__ = "projections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    week_start: Mapped[date] = mapped_column(Date, unique=True)
    data: Mapped[dict] = mapped_column(JSONB)  # DailyProjection[] 完整7天配置
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
