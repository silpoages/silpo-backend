import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GoodPracticeCompletionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    good_practice_id: uuid.UUID
    completed_at: datetime = Field(validation_alias="posted_at")
