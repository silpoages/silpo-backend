from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity


class ActivityService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_available(self) -> list[Activity]:
        query = await self.db.execute(
            select(Activity).where(
                Activity.enabled.is_(True),
                Activity.deleted_at.is_(None),
            )
        )
        return list(query.scalars().all())
