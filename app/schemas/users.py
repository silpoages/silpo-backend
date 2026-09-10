from pydantic import BaseModel, ConfigDict, EmailStr

from app.enums import Role


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email: str
    role: Role
    onboarding_completed: bool
