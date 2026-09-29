import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ActivityReadBase(BaseModel):
    id: uuid.UUID
    name: str
    max_duration_seconds: int | None


class BreathingConfiguration(BaseModel):
    inhale_seconds: int
    hold_seconds: int
    exhale_seconds: int
    repeat_count: int | None


class BreathingActivityRead(ActivityReadBase):
    type: Literal["breathing"]
    breathing: BreathingConfiguration


class MeditationConfiguration(BaseModel):
    audio_url: str


class MeditationActivityRead(ActivityReadBase):
    type: Literal["meditation"]
    meditation: MeditationConfiguration


class SelfRegulationConfiguration(BaseModel):
    bubble_spawn_interval_ms: int


class SelfRegulationActivityRead(ActivityReadBase):
    type: Literal["self_regulation"]
    self_regulation: SelfRegulationConfiguration


ActivityRead = Annotated[
    BreathingActivityRead | MeditationActivityRead | SelfRegulationActivityRead,
    Field(discriminator="type"),
]