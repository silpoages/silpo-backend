from typing import Literal

from pydantic import BaseModel

DashboardActivityId = Literal[
    "breathing",
    "diary",
    "meditation",
    "good_practice",
    "self_regulation",
]


class DashboardActivityRead(BaseModel):
    id: DashboardActivityId
    name: str
    executions: int


class DashboardActivityResponse(BaseModel):
    top_activities: list[DashboardActivityRead]
