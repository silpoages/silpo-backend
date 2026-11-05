from pydantic import BaseModel

from app.enums import Gender


class AgeRangeDistribution(BaseModel):
    age_range: str
    count: int
    percentage: float


class GenderDistribution(BaseModel):
    gender: Gender
    count: int
    percentage: float


class DashboardSummaryResponse(BaseModel):
    total_users: int
    premium_active_users: int
    age_distribution: list[AgeRangeDistribution]
    gender_distribution: list[GenderDistribution]
