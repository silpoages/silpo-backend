import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.enums import Gender, Role
from app.models.user import User
from app.services.email_confirmation import EmailConfirmationService
from app.services.password_reset import PasswordResetService


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_active_user(self, user_id: uuid.UUID) -> User:
        user = await self.db.get(User, user_id)
        if user is None or not user.enabled or user.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user

    async def get_active_admin(self, user_id: uuid.UUID) -> User:
        user = await self.get_active_user(user_id)
        if user.role != Role.ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
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
        await self._commit_or_conflict()
        await self.db.refresh(user)

        await EmailConfirmationService(self.db).create_and_send(user)

        return user

    async def _commit_or_conflict(self) -> None:
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

    async def create_by_admin(self, payload: dict[str, Any]) -> User:
        # Ninguém conhece esta senha: o usuário define a dele pelo link de redefinição
        # enviado logo abaixo, o que também confirma o e-mail.
        user = User(
            **{**payload, "email": payload["email"].strip().lower()},
            password=hash_password(secrets.token_urlsafe(32)),
            role=Role.USER,
        )
        self.db.add(user)
        await self._commit_or_conflict()
        await self.db.refresh(user)

        await PasswordResetService(self.db).request_reset(user.email)

        return user

    async def update_by_admin(
        self, user_id: uuid.UUID, payload: dict[str, Any], current_admin: User
    ) -> User:
        user = await self.get_user_by_id(user_id)

        if user.id == current_admin.id and payload.get("enabled") is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Você não pode desativar a própria conta",
            )

        if "email" in payload:
            payload["email"] = payload["email"].strip().lower()
        for field, value in payload.items():
            setattr(user, field, value)

        await self._commit_or_conflict()
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

        new_password = payload.get("new_password")
        if new_password is not None:
            current_password = payload.get("current_password")
            if not user.password or not verify_password(current_password or "", user.password):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Current password is incorrect",
                )
            user.password = hash_password(new_password)

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

        if not user.password or not verify_password(password, user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        if get_settings().is_production and user.email_confirmed_at is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not confirmed",
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

    async def list_users(
        self,
        page: int,
        page_size: int,
        search: str | None = None,
        role: Role | None = None,
        enabled: bool | None = None,
        gender: Gender | None = None,
    ) -> tuple[list[User], int]:
        query = select(User)

        if search and search.strip():
            pattern = f"%{search.strip()}%"
            query = query.where(or_(User.full_name.ilike(pattern), User.email.ilike(pattern)))
        if role is not None:
            query = query.where(User.role == role)
        if enabled is not None:
            query = query.where(User.enabled == enabled)
        if gender is not None:
            query = query.where(User.gender == gender)

        total = await self.db.scalar(select(func.count()).select_from(query.subquery()))

        result = await self.db.execute(
            query.order_by(User.created_at.desc(), User.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total or 0

    async def get_user_by_id(self, user_id: uuid.UUID) -> User:
        user = await self.db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user
