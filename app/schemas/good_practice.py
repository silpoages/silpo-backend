import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GoodPracticeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # min_length roda depois do strip, então título ou descrição só com espaço vira 422.
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    enabled: bool = True


class GoodPracticeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str


class GoodPracticeAdminRead(GoodPracticeRead):
    enabled: bool


class GoodPracticeListResponse(BaseModel):
    items: list[GoodPracticeRead]


class GoodPracticeCompletionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    good_practice_id: uuid.UUID
    completed_at: datetime = Field(validation_alias="posted_at")
