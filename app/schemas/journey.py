from datetime import date

from pydantic import BaseModel

from app.enums import Mood


class JourneyPeriod(BaseModel):
    month: str
    start_date: date
    end_date: date


class JourneySummary(BaseModel):
    mood_days: int
    different_good_practices: int
    completed_activities: int


class JourneyMoodCount(BaseModel):
    mood: Mood
    count: int


class JourneyAchievements(BaseModel):
    unlocked: int
    total: int


class JourneyRead(BaseModel):
    period: JourneyPeriod
    summary: JourneySummary
    mood_distribution: list[JourneyMoodCount]
    achievements: JourneyAchievements
