from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, security
from app.db.session import get_db
from app.models.user import User
from app.services.mood_logs import MoodLogService
from app.services.template import TemplateService

DbSession = AsyncGenerator[AsyncSession, None]

get_session = get_db


def get_template_service(db: AsyncSession = Depends(get_session)) -> TemplateService:
    return TemplateService(db)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_session),
) -> User:
    token = credentials.credentials
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    user = await db.get(User, payload["sub"])
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


def get_mood_log_service(db: AsyncSession = Depends(get_session)) -> MoodLogService:
    return MoodLogService(db)