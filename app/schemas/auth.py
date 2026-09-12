import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.enums import Role


class RegisterInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class RegisterOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: Role
    onboarding_completed: bool


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class LoginUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None
    role: Role
    onboarding_completed: bool


class LoginOutput(BaseModel):
    access_token: str
    token_type: str
    user: LoginUser
