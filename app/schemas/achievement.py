import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.enums import AchievementCategory


class AchievementProgress(BaseModel):
    current: int = Field(ge=0, description="Quantidade já realizada, limitada à meta.")
    target: int = Field(ge=1, description="Quantidade necessária para desbloquear.")


class AchievementRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    icon: str = Field(description="Nome do ícone Ionicons usado pelo app.")
    category: AchievementCategory
    unlocked: bool
    progress: AchievementProgress
    unlocked_at: datetime | None = Field(description="Data do desbloqueio; `null` se bloqueada.")


class AchievementListResponse(BaseModel):
    items: list[AchievementRead]
