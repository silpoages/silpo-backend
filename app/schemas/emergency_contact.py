import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EmergencyContactCreate(BaseModel):
    full_name: str
    phone_number: str
    image_url: str | None = None


class EmergencyContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    phone_number: str
    image_url: str | None = None
    created_at: datetime


class EmergencyContactListResponse(BaseModel):
    contacts: list[EmergencyContactRead]
