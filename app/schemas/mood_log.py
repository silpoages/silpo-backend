import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.enums import Mood


class MoodLogCreate(BaseModel):
    mood: Mood


class MoodLogGet(BaseModel):
    date: date


class MoodLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mood: Mood
    posted_at: datetime


class MoodLogListResponse(BaseModel):
    items: list[MoodLogItem]


class MoodLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    mood: Mood
    posted_at: datetime
