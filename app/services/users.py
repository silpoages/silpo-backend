import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.enums import Gender, Role
from app.models.user import User


class UsersService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_active_user(self, user_id: uuid.UUID) -> User:
        user = await self.db.get(User, user_id)
        if user is None or not user.enabled or user.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user

    async def register(self, email: str, password: str) -> User:
        user = User(
            email=email.strip().lower(),
            password=hash_password(password),
            role=Role.USER,
            gender=Gender.PREFER_NOT_TO_SAY,
            onboarding_completed=False,
        )
        self.db.add(user)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            original = exc.orig
            if original is not None:
                original = original.__cause__ or original
            constraint = getattr(original, "constraint_name", None)
            if constraint == "user_email_key":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email já cadastrado",
                ) from exc
            raise
        await self.db.refresh(user)
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
