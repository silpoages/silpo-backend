import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

_NON_NULL_UPDATE_FIELDS = ("name", "description", "audio_url", "max_duration_seconds", "enabled")


class MeditationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=300)
    audio_url: str = Field(min_length=1)
    max_duration_seconds: int = Field(gt=0)
    enabled: bool = True


class MeditationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, min_length=1, max_length=300)
    audio_url: str | None = Field(default=None, min_length=1)
    max_duration_seconds: int | None = Field(default=None, gt=0)
    enabled: bool | None = None

    @model_validator(mode="after")
    def _reject_explicit_null(self) -> "MeditationUpdate":
        for field in _NON_NULL_UPDATE_FIELDS:
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class MeditationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    audio_url: str
    max_duration_seconds: int | None
    enabled: bool


class MeditationListResponse(BaseModel):
    items: list[MeditationRead]
    total: int
    page: int
    page_size: int
