import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.db.session import get_db
from app.models.user import User
from app.services.email_confirmation import EmailConfirmationService
from app.services.emergency_contact import EmergencyContactService
from app.services.mood_log import MoodLogService
from app.services.user import UserService

DbSession = AsyncGenerator[AsyncSession, None]

get_session = get_db


def get_mood_log_service(db: AsyncSession = Depends(get_session)) -> MoodLogService:
    return MoodLogService(db)


def get_user_service(db: AsyncSession = Depends(get_session)) -> UserService:
    return UserService(db)


def get_emergency_contact_service(
    db: AsyncSession = Depends(get_session),
) -> EmergencyContactService:
    return EmergencyContactService(db)


def get_email_confirmation_service(
    db: AsyncSession = Depends(get_session),
) -> EmailConfirmationService:
    return EmailConfirmationService(db)


async def get_current_user(
    user_id: uuid.UUID = Depends(get_current_user_id),
    user_service: UserService = Depends(get_user_service),
) -> User:
    return await user_service.get_active_user(user_id)
