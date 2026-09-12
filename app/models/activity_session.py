import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.enums import ActivityType


class ActivitySession(Base):
    __tablename__ = "activity_session"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )
    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity.id"), nullable=False
    )
    type: Mapped[ActivityType] = mapped_column(
        Enum(
            ActivityType, name="activity_type", values_callable=lambda enum: [e.value for e in enum]
        ),
        nullable=False,
    )
    time_spent_seconds: Mapped[int] = mapped_column(nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __mapper_args__ = {"polymorphic_on": type}
