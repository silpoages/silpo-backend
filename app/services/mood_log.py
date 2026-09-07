import uuid
from datetime import datetime

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
        mood_log.posted_at = datetime.now()
        
        self.db.add(mood_log)
        await self.db.commit()
        await self.db.refresh(mood_log)
        return mood_log
