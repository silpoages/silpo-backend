import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TemplateBase(BaseModel):
    name: str
    description: str | None = None


class TemplateCreate(TemplateBase):
    pass


class TemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class TemplateRead(TemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
