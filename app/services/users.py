import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UsersService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_user(self, user_id: uuid.UUID) -> User:
        user = await self.db.get(User, user_id)
        if user is None or not user.enabled or user.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user

    async def update_user(self, user_id: uuid.UUID, payload: dict[str, Any]) -> User:
        user = await self.db.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        user.full_name = payload.get("full_name", user.full_name)
        user.birth_date = payload.get("birth_date", user.birth_date)
        user.gender = payload.get("gender", user.gender)
        user.email = user.email
        user.daily_reminder_enabled = payload.get(
            "daily_reminder_enabled", user.daily_reminder_enabled
        )
        user.onboarding_completed = True

        await self.db.commit()
        await self.db.refresh(user)
        return user
