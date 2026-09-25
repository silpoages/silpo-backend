import uuid

from pydantic import BaseModel, ConfigDict


class GoodPracticeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str


class GoodPracticeListResponse(BaseModel):
    items: list[GoodPracticeRead]
