import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.enums import Mood


class DiaryImageRead(BaseModel):
    image_url: str


class DiaryEntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    note: str = Field(min_length=1)
    entry_date: date | None = None
    mood: Mood | None = None
    mood_log_id: uuid.UUID | None = None
    image_url: str | None = None

    @model_validator(mode="after")
    def mood_source_is_exclusive(self) -> Self:
        if self.mood is not None and self.mood_log_id is not None:
            raise ValueError("Send mood or mood_log_id, not both")
        return self


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
    page: int = 1
    page_size: int = 10
    total: int = 0


class DiaryDeletedEntryRead(DiaryEntryRead):
    deleted_at: datetime


class DiaryDeletedEntryListResponse(BaseModel):
    items: list[DiaryDeletedEntryRead]
    page: int = 1
    page_size: int = 10
    total: int = 0


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
    moods: list[Mood] = Field(default_factory=list)


class DiaryMonthSummary(BaseModel):
    year: int
    month: int
    days: list[DiaryCalendarDay]
