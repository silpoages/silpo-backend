import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DailyMessageCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=140)
    enabled: bool = True


class DailyMessageUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str | None = Field(default=None, min_length=1, max_length=140)
    enabled: bool | None = None


class DailyMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message: str
    enabled: bool
    last_shown: datetime | None
    created_at: datetime


class DailyMessageListResponse(BaseModel):
    items: list[DailyMessageRead]
    page: int
    page_size: int
    total: int
    enabled: int
    disabled: int
