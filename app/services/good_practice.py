import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.good_practice import GoodPractice
from app.models.good_practice_log import GoodPracticeLog


class GoodPracticeService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_enabled(self) -> list[GoodPractice]:
        result = await self.db.execute(
            select(GoodPractice)
            .where(
                GoodPractice.enabled.is_(True),
                GoodPractice.deleted_at.is_(None),
            )
            .order_by(GoodPractice.id)
        )
        return list(result.scalars().all())

    async def list_for_admin(
        self,
        page: int,
        page_size: int,
        search: str | None = None,
        enabled: bool | None = None,
    ) -> tuple[list[GoodPractice], int]:
        query = select(GoodPractice).where(GoodPractice.deleted_at.is_(None))

        if search and search.strip():
            pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    GoodPractice.title.ilike(pattern),
                    GoodPractice.description.ilike(pattern),
                )
            )

        if enabled is not None:
            query = query.where(GoodPractice.enabled == enabled)

        total = await self.db.scalar(select(func.count()).select_from(query.subquery()))

        result = await self.db.execute(
            query.order_by(GoodPractice.created_at.desc(), GoodPractice.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        return list(result.scalars().all()), total or 0

    async def get_daily(self) -> GoodPractice | None:
        practices = await self.list_enabled()
        if not practices:
            return None

        index = datetime.now(UTC).date().toordinal() % len(practices)
        return practices[index]

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
