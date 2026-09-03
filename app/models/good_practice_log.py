import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GoodPracticeLog(Base):
    __tablename__ = "good_practice_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    good_practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("good_practice.id"), nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)