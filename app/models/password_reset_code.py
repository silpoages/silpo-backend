import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.enums import PasswordResetMethod


class PasswordResetCode(Base):
    __tablename__ = "password_reset_code"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    method: Mapped[PasswordResetMethod] = mapped_column(
        Enum(
            PasswordResetMethod,
            name="password_reset_method",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        server_default=PasswordResetMethod.LINK.value,
    )
    # Wrong guesses against a CODE; the code stops working once it reaches the limit.
    failed_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
