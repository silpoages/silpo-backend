from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

DbSession = AsyncGenerator[AsyncSession, None]

get_session = get_db
