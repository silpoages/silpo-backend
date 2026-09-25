from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.good_practice import GoodPractice


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

    async def get_daily(self) -> GoodPractice | None:
        practices = await self.list_enabled()
        if not practices:
            return None

        index = date.today().toordinal() % len(practices)
        return practices[index]
