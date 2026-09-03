import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.enums import Gender, Role


class User(Base):
    __tablename__ = "user"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    gender: Mapped[Gender] = mapped_column(Enum(Gender, name="gender"), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_number: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    role: Mapped[Role] = mapped_column(Enum(Role, name="role"), nullable=False)
    profile_picture_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
