import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.db.session import get_db
from app.services.auth import AuthService
from app.services.emergency_contact import EmergencyContactService
from app.services.template import TemplateService
from app.models.user import User
from app.services.mood_log import MoodLogService
from app.services.users import UsersService

DbSession = AsyncGenerator[AsyncSession, None]

get_session = get_db


def get_template_service(db: AsyncSession = Depends(get_session)) -> TemplateService:
    return TemplateService(db)


def get_auth_service(db: AsyncSession = Depends(get_session)) -> AuthService:
    return AuthService(db)


def get_emergency_contact_service(
    db: AsyncSession = Depends(get_session),
) -> EmergencyContactService:
    return EmergencyContactService(db)
