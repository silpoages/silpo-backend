import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SelfRegulationActivity(Base):
    __tablename__ = "self_regulation_activity"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity.id"), primary_key=True
    )
    bubble_spawn_interval_ms: Mapped[int] = mapped_column(nullable=False)
