import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meditation_activity import MeditationActivity
from app.schemas.meditation import MeditationCreate, MeditationUpdate


class MeditationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, payload: MeditationCreate) -> MeditationActivity:
        meditation = MeditationActivity(
            name=payload.name,
            description=payload.description,
            audio_url=payload.audio_url,
            max_duration_seconds=payload.max_duration_seconds,
            enabled=payload.enabled,
        )
        self.db.add(meditation)
        await self.db.commit()
        await self.db.refresh(meditation)
        return meditation

    async def list_enabled(self) -> list[MeditationActivity]:
        result = await self.db.execute(
            select(MeditationActivity)
            .where(
                MeditationActivity.enabled.is_(True),
                MeditationActivity.deleted_at.is_(None),
            )
            .order_by(MeditationActivity.created_at.desc(), MeditationActivity.id)
        )
        return list(result.scalars().all())

    async def list_for_admin(
        self,
        page: int,
        page_size: int,
        search: str | None = None,
        enabled: bool | None = None,
    ) -> tuple[list[MeditationActivity], int]:
        query = select(MeditationActivity).where(MeditationActivity.deleted_at.is_(None))

        if search and search.strip():
            pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    MeditationActivity.name.ilike(pattern),
                    MeditationActivity.description.ilike(pattern),
                )
            )

        if enabled is not None:
            query = query.where(MeditationActivity.enabled == enabled)

        total = await self.db.scalar(select(func.count()).select_from(query.subquery()))

        result = await self.db.execute(
            query.order_by(MeditationActivity.created_at.desc(), MeditationActivity.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        return list(result.scalars().all()), total or 0

    async def get_by_id(self, meditation_id: uuid.UUID) -> MeditationActivity:
        result = await self.db.execute(
            select(MeditationActivity).where(
                MeditationActivity.id == meditation_id,
                MeditationActivity.deleted_at.is_(None),
            )
        )
        meditation = result.scalar_one_or_none()
        if meditation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Meditation not found"
            )
        return meditation

    async def get_enabled(self, meditation_id: uuid.UUID) -> MeditationActivity:
        result = await self.db.execute(
            select(MeditationActivity).where(
                MeditationActivity.id == meditation_id,
                MeditationActivity.enabled.is_(True),
                MeditationActivity.deleted_at.is_(None),
            )
        )
        meditation = result.scalar_one_or_none()
        if meditation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Meditation not found"
            )
        return meditation

    async def update(self, meditation_id: uuid.UUID, payload: MeditationUpdate) -> MeditationActivity:
        meditation = await self.get_by_id(meditation_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(meditation, field, value)

        await self.db.commit()
        await self.db.refresh(meditation)
        return meditation

    async def delete(self, meditation_id: uuid.UUID) -> None:
        meditation = await self.get_by_id(meditation_id)
        meditation.enabled = False
        meditation.deleted_at = datetime.now(UTC)
        await self.db.commit()
