import uuid
from datetime import date

from sqlalchemy import Date, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mood.log import MoodLog


class MoodLogService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_user(self, user_id: uuid.UUID, log_date: date | None = None) -> list[MoodLog]:
        query = select(MoodLog).where(MoodLog.user_id == user_id)

        if log_date:
            query = query.where(cast(MoodLog.posted_at, Date) == log_date)

        query = query.order_by(MoodLog.posted_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())
