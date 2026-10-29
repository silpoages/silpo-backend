import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.enums import Gender, Role


class UserCreate(BaseModel):
    full_name: str
    birth_date: date
    gender: Gender
    daily_reminder_enabled: bool
    # Optional password change: both must be set together. current_password is required
    # so a stolen/leaked access token alone can't be used to take over the account.
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=8)

    @model_validator(mode="after")
    def _validate_password_change(self) -> "UserCreate":
        if (self.current_password is None) != (self.new_password is None):
            raise ValueError("current_password and new_password must be provided together")
        return self


class UserRead(BaseModel):
    full_name: str
    birth_date: date
    gender: Gender
    email: str
    daily_reminder_enabled: bool
    onboarding_completed: bool

    model_config = ConfigDict(from_attributes=True)


class UserDeleteResponse(BaseModel):
    message: str


class AdminUserRead(BaseModel):
    id: uuid.UUID
    full_name: str | None
    email: str
    birth_date: date | None
    gender: Gender
    role: Role
    enabled: bool
    onboarding_completed: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminUserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # min_length roda depois do strip, então nome só com espaço vira 422.
    full_name: str = Field(min_length=1)
    email: EmailStr
    birth_date: date | None = None
    gender: Gender = Gender.PREFER_NOT_TO_SAY
    enabled: bool = True


class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str | None = Field(default=None, min_length=1)
    email: EmailStr | None = None
    birth_date: date | None = None
    gender: Gender | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def _reject_explicit_null(self) -> "AdminUserUpdate":
        # Ausente = não altera; null só é aceito em birth_date, a única coluna opcional aqui.
        for field in self.model_fields_set - {"birth_date"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class AdminUserListResponse(BaseModel):
    items: list[AdminUserRead]
    total: int
    page: int
    page_size: int
