import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.enums import Mood


class MoodLog(Base):
    __tablename__ = "mood_log"
    __table_args__ = (UniqueConstraint("user_id", "log_date", name="uq_mood_log_user_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True
    )
    mood: Mapped[Mood] = mapped_column(
        Enum(Mood, name="mood", values_callable=lambda enum: [e.value for e in enum]),
        nullable=False,
    )
    # Data (UTC) do registro, separada de `posted_at` para permitir a constraint de
    # "1 mood por usuário por dia" independente do device/horário de envio.
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
