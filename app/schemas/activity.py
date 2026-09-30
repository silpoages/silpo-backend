import uuid

from pydantic import BaseModel, ConfigDict, field_validator

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
