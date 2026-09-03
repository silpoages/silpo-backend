import uuid

from sqlalchemy import Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

class BreathActivity(Base):
    __tablename__ = "breath_activity"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("activity.id"), primary_key=True)
    inhale_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    hold_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    exhale_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    repeat_count: Mapped[int | None] = mapped_column(Integer, nullable=True)