import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.enums import Gender, Role


class User(Base):
    __tablename__ = "user"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str | None] = mapped_column(Text)
    gender: Mapped[Gender] = mapped_column(
        Enum(Gender, name="gender", values_callable=lambda enum: [e.value for e in enum]),
        nullable=False,
        server_default=text(f"'{Gender.PREFER_NOT_TO_SAY.value}'"),
    )
    birth_date: Mapped[date | None] = mapped_column(Date)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password: Mapped[str] = mapped_column(Text, nullable=False)
    phone_number: Mapped[str | None] = mapped_column(Text, unique=True)
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="role", values_callable=lambda enum: [e.value for e in enum]),
        nullable=False,
        server_default=text(f"'{Role.USER.value}'"),
    )
    profile_picture_url: Mapped[str | None] = mapped_column(Text)
    plan_end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
