from sqlalchemy import String, Boolean, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from ..database import Base


class CarpoolGroup(Base):
    __tablename__ = "carpool_groups"

    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CarpoolMember(Base):
    __tablename__ = "carpool_members"

    group_id: Mapped[str] = mapped_column(String(10), ForeignKey("carpool_groups.id", ondelete="CASCADE"), primary_key=True)
    dealer_id: Mapped[str] = mapped_column(String(10), ForeignKey("dealers.id", ondelete="CASCADE"), primary_key=True)
    is_driver: Mapped[bool] = mapped_column(Boolean, default=False)
