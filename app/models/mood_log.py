import uuid
from datetime import datetime

from app.enums import Mood

from sqlalchemy import DateTime, ForeignKey, func, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

class MoodLog(Base):
    __tablename__ = "mood_log"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    mood: Mapped[Mood] = mapped_column(Enum(Mood, name="mood"), nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)