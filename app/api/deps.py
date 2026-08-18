from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.template import TemplateService

DbSession = AsyncGenerator[AsyncSession, None]

get_session = get_db


def get_template_service(db: AsyncSession = Depends(get_session)) -> TemplateService:
    return TemplateService(db)
