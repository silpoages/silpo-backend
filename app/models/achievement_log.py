import uuid
from datetime import datetime

from sqlalchemy import DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

class AchievementLog(Base):
    __tablename__ = "achievement_log"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    achievement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("achievement.id"), nullable=False)
    achieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)