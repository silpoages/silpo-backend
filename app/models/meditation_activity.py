import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MeditationActivity(Base):
    __tablename__ = "meditation_activity"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity.id"), primary_key=True
    )
    audio_url: Mapped[str] = mapped_column(Text, nullable=False)
