import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

_NOT_NULL_FIELDS = ("name", "description", "audio_url", "enabled")


class MeditationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # min_length roda depois do strip, então nome/descrição/áudio só com espaço vira 422.
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    audio_url: str = Field(min_length=1)
    max_duration_seconds: int | None = Field(default=None, gt=0)
    enabled: bool = True


class MeditationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, min_length=1)
    audio_url: str | None = Field(default=None, min_length=1)
    max_duration_seconds: int | None = Field(default=None, gt=0)
    enabled: bool | None = None

    @model_validator(mode="after")
    def _reject_explicit_null(self) -> "MeditationUpdate":
        # name, description, audio_url e enabled são NOT NULL no banco: ausente = não
        # altera, null = 422. max_duration_seconds é nullable, então pode ser limpo.
        for field in _NOT_NULL_FIELDS:
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
