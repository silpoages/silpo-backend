import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GoodPracticeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None

    @model_validator(mode="after")
    def _reject_explicit_null(self) -> "GoodPracticeUpdate":
        # Campos são NOT NULL no banco: ausente = não altera, null = 422.
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class GoodPracticeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    completed_today: bool | None = None


class GoodPracticeAdminRead(BaseModel):
    """Visão do admin: sem `completed_today`, que só faz sentido para o usuário do app."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    enabled: bool


class GoodPracticeListResponse(BaseModel):
    items: list[GoodPracticeRead]


class GoodPracticeAdminListResponse(BaseModel):
    items: list[GoodPracticeAdminRead]
    total: int
    page: int
    page_size: int


class GoodPracticeCompletionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    good_practice_id: uuid.UUID
    completed_at: datetime = Field(validation_alias="posted_at")
