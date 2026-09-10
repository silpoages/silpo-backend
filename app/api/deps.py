from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.template import TemplateService

DbSession = AsyncGenerator[AsyncSession, None]

get_session = get_db


def get_template_service(db: AsyncSession = Depends(get_session)) -> TemplateService:
    return TemplateService(db)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_session),
) -> User:
    token = credentials.credentials


def get_mood_log_service(db: AsyncSession = Depends(get_session)) -> MoodLogService:
    return MoodLogService(db)
