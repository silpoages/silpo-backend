from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.enums import Gender


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
