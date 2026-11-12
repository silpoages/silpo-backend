import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.enums import Mood


class DiaryEntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    note: str = Field(min_length=1)
    entry_date: date | None = None
    mood_log_id: uuid.UUID | None = None
    image_url: str | None = None


class DiaryEntryPractice(BaseModel):
    id: uuid.UUID
    title: str


class DiaryEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entry_date: date
    note: str
    image_url: str | None
    mood_log_id: uuid.UUID | None
    mood: Mood | None
    practice: DiaryEntryPractice | None = None
    created_at: datetime


class DiaryEntryListResponse(BaseModel):
    items: list[DiaryEntryRead]


class DiaryMoodLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mood: Mood
    log_date: date
    posted_at: datetime


class DiaryMoodLogListResponse(BaseModel):
    items: list[DiaryMoodLogRead]


class DiaryCalendarDay(BaseModel):
    entry_date: date
    entries_count: int


class DiaryMonthSummary(BaseModel):
    year: int
    month: int
    days: list[DiaryCalendarDay]
