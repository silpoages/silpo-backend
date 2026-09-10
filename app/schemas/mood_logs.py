import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.enums import Mood


class MoodLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mood: Mood
    posted_at: datetime


class MoodLogListResponse(BaseModel):
    items: list[MoodLogItem]
