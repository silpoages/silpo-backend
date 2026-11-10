import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Mood
from app.models.mood_log import MoodLog


class MoodLogService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_today(self, user_id: uuid.UUID) -> MoodLog | None:
        today = datetime.now(UTC).date()
        result = await self.db.execute(
            select(MoodLog)
            .where(MoodLog.user_id == user_id, MoodLog.log_date == today)
            .order_by(MoodLog.posted_at.desc(), MoodLog.id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(self, user_id: uuid.UUID, mood: Mood) -> MoodLog:
        now = datetime.now(UTC)

        mood_log = MoodLog()
        mood_log.user_id = user_id
        mood_log.mood = mood
        mood_log.log_date = now.date()
        mood_log.posted_at = now

        self.db.add(mood_log)

        await self.db.commit()
        await self.db.refresh(mood_log)
        return mood_log

    async def list_by_date(self, user_id: uuid.UUID, log_date: date | None) -> list[MoodLog]:
        query = select(MoodLog).where(MoodLog.user_id == user_id)

        if log_date is not None:
            query = query.where(MoodLog.log_date == log_date)

        query = query.order_by(MoodLog.posted_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())
