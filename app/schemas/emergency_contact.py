import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EmergencyContactBase(BaseModel):
    full_name: str
    nickname: str
    phone_number: str
    image_url: str | None = None


class EmergencyContactCreate(EmergencyContactBase):
    pass


class EmergencyContactRead(EmergencyContactBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
