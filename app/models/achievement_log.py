import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AchievementLog(Base):
    __tablename__ = "achievement_log"
    # Uma conquista é desbloqueada uma única vez por usuário, mesmo com requisições concorrentes.
    __table_args__ = (
        UniqueConstraint("user_id", "achievement_id", name="uq_achievement_log_user_achievement"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True
    )
    achievement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("achievement.id"), nullable=False, index=True
    )
    achieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """Quando o usuário viu o alerta do desbloqueio; `None` enquanto o alerta está pendente."""
