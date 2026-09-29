import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.enums import ActivityType

_ACTIVITY_TYPE_LABELS: dict[ActivityType, str] = {
    ActivityType.BREATHING: "breathing",
    ActivityType.MEDITATION: "meditation",
    ActivityType.SELF_REGULATION: "selfregulation",
}


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: str
    max_duration_seconds: int | None = None

    @field_validator("type", mode="before")
    @classmethod
    def _map_type(cls, value: object) -> object:
        if isinstance(value, ActivityType):
            return _ACTIVITY_TYPE_LABELS[value]
        return value


class ActivityListResponse(BaseModel):
    items: list[ActivityRead]


class ActivityConfigurationBase(BaseModel):
    id: uuid.UUID
    name: str
    max_duration_seconds: int | None


class BreathingConfiguration(BaseModel):
    inhale_seconds: int
    hold_seconds: int
    exhale_seconds: int
    repeat_count: int | None


class BreathingActivityRead(ActivityConfigurationBase):
    type: Literal["breathing"]
    breathing: BreathingConfiguration


class MeditationConfiguration(BaseModel):
    audio_url: str


class MeditationActivityRead(ActivityConfigurationBase):
    type: Literal["meditation"]
    meditation: MeditationConfiguration


class SelfRegulationConfiguration(BaseModel):
    bubble_spawn_interval_ms: int


class SelfRegulationActivityRead(ActivityConfigurationBase):
    type: Literal["self_regulation"]
    self_regulation: SelfRegulationConfiguration


ActivityConfigurationRead = Annotated[
    BreathingActivityRead | MeditationActivityRead | SelfRegulationActivityRead,
    Field(discriminator="type"),
]
