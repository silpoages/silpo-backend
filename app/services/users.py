import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, pwd_context
from app.models.user import User


class UsersService:
    def __init__(self, db: AsyncSession):
        self.db = db

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

    async def login(self, email: str, password: str) -> dict[str, Any]:
        normalized_email = email.strip().lower()

        result = await self.db.execute(select(User).where(User.email == normalized_email))
        user = result.scalar_one_or_none()

        if user is None or not user.enabled or user.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        if not user.password or not pwd_context.verify(password, user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        token = create_access_token(str(user.id))

        return {
            "access_token": token,
            "token_type": "bearer",  # nosec B105 - fixed auth scheme
            "user": user,
        }

    async def delete(self, user_id: uuid.UUID) -> bool:
        user = await self.db.get(User, user_id)

        if user is None or not user.enabled:
            return False

        user.enabled = False
        user.deleted_at = datetime.now(UTC)
        await self.db.commit()

        return True
