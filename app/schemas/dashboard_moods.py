from datetime import date
from enum import IntEnum

from pydantic import BaseModel

from app.enums import Mood


class PeriodDays(IntEnum):
    SEVEN = 7
    THIRTY = 30
    NINETY = 90


class DailyMoodCounts(BaseModel):
    day: date
    counts: dict[Mood, int]


class MoodDistribution(BaseModel):
    mood: Mood
    count: int
    percentage: float


class DashboardMoodsResponse(BaseModel):
    period_days: int
    total_records: int
    daily: list[DailyMoodCounts]
    distribution: list[MoodDistribution]
