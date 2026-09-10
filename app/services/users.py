from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.enums import Gender, Role
from app.models.user import User
from app.schemas.users import UserCreate


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, payload: UserCreate) -> User:
        user = User(
            email=payload.email,
            password=hash_password(payload.password),
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
