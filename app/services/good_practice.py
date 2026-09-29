import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.good_practice import GoodPractice
from app.models.good_practice_log import GoodPracticeLog


class GoodPracticeService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_enabled(self, good_practice_id: uuid.UUID) -> GoodPractice:
        result = await self.db.execute(
            select(GoodPractice).where(
                GoodPractice.id == good_practice_id,
                GoodPractice.enabled.is_(True),
                GoodPractice.deleted_at.is_(None),
            )
        )
        good_practice = result.scalar_one_or_none()
        if good_practice is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Good practice not found"
            )
        return good_practice

    async def complete(self, user_id: uuid.UUID, good_practice_id: uuid.UUID) -> GoodPracticeLog:
        good_practice = await self.get_enabled(good_practice_id)

        good_practice_log = GoodPracticeLog()
        good_practice_log.user_id = user_id
        good_practice_log.good_practice_id = good_practice.id
        good_practice_log.posted_at = datetime.now(UTC)

        self.db.add(good_practice_log)
        await self.db.commit()
        await self.db.refresh(good_practice_log)
        return good_practice_log
