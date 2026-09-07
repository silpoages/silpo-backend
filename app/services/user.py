import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = get_settings()


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _create_access_token(self, user_id: str) -> str:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
        payload = {
            "sub": user_id,
            "exp": expires_at,
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    async def login(self, email: str, password: str) -> dict:
        normalized_email = email.strip().lower()

        result = await self.db.execute(select(User).where(User.email == normalized_email))
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        if not user.enabled or user.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        if not user.password or not pwd_context.verify(password, user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        token = self._create_access_token(str(user.id))

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "full_name": user.full_name,
                "email": user.email,
                "role": user.role.value,
            },
        }

    async def delete(self, user_id: uuid.UUID) -> bool:
        user = await self.db.get(User, user_id)

        if user is None:
            return False

        user.enabled = False
        user.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()

        return True