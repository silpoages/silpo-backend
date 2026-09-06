import re

from pydantic import BaseModel, ConfigDict, field_validator

from app.enums import Role

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserCreate(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, email: str) -> str:
        if not EMAIL_REGEX.match(email):
            raise ValueError("email inválido")
        return email


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email: str
    role: Role
    onboarding_completed: bool
