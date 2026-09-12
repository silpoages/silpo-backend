from datetime import datetime 
from pydantic import BaseModel, ConfigDict
from app.enums import Gender

class UserCreate(BaseModel):
    full_name: str
    birth_date: datetime 
    gender: Gender
    daily_reminder_enabled: bool 

class UserRead(BaseModel):
    full_name: str
    birth_date: datetime 
    gender: Gender
    email: str
    daily_reminder_enabled: bool 
    onboarding_completed: bool

    model_config = ConfigDict(from_attributes=True)