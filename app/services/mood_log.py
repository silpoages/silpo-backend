import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Date, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Mood
from app.models.mood_log import MoodLog


class MoodLogService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, user_id: uuid.UUID, mood: Mood) -> MoodLog:
        mood_log = MoodLog()
        mood_log.user_id = user_id
        mood_log.mood = mood
        mood_log.posted_at = datetime.now(UTC)

        self.db.add(mood_log)
        await self.db.commit()
        await self.db.refresh(mood_log)
        return mood_log

    async def list_by_date(self, user_id: uuid.UUID, log_date: date) -> list[MoodLog]:
        query = select(MoodLog).where(MoodLog.user_id == user_id)

        if log_date:
            query = query.where(cast(MoodLog.posted_at, Date) == log_date)

        query = query.order_by(MoodLog.posted_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())
