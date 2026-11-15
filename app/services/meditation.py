import logging
import re
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.meditation_activity import MeditationActivity
from app.schemas.meditation import MeditationBase, MeditationCreate, MeditationUpdate
from app.services.audio_storage import AudioStorage

logger = logging.getLogger(__name__)

MEDITATION_AUDIO_ROUTE_PREFIX = "/media/meditations"

_AUDIO_KEY_PATTERN = re.compile(r"^[0-9a-f]{32}\.mp3$")


def build_audio_key() -> str:
    return f"{uuid.uuid4().hex}.mp3"


def build_audio_url(key: str) -> str:
    base_url = get_settings().api_base_url.rstrip("/")
    return f"{base_url}{MEDITATION_AUDIO_ROUTE_PREFIX}/{key}"


def audio_key_from_url(audio_url: str) -> str | None:
    prefix = f"{get_settings().api_base_url.rstrip('/')}{MEDITATION_AUDIO_ROUTE_PREFIX}/"
    if not audio_url.startswith(prefix):
        return None
    key = audio_url.removeprefix(prefix)
    return key if _AUDIO_KEY_PATTERN.fullmatch(key) else None


class MeditationService:
    def __init__(self, db: AsyncSession, storage: AudioStorage | None = None) -> None:
        self.db = db
        self.storage = storage

    async def create(self, payload: MeditationCreate) -> MeditationActivity:
        meditation = await self._insert(payload)
        await self.db.refresh(meditation)
        return meditation

    async def _insert(self, payload: MeditationCreate) -> MeditationActivity:
        meditation = MeditationActivity(
            name=payload.name,
            description=payload.description,
            audio_url=payload.audio_url,
            max_duration_seconds=payload.max_duration_seconds,
            enabled=payload.enabled,
        )
        self.db.add(meditation)
        await self.db.commit()
        return meditation

    async def create_with_audio(self, form: MeditationBase, audio: bytes) -> MeditationActivity:
        if self.storage is None:
            raise RuntimeError("MeditationService needs an AudioStorage to upload audio")

        key = build_audio_key()
        await self.storage.save(key, audio)

        payload = MeditationCreate(**form.model_dump(), audio_url=build_audio_url(key))
        # Only undo the upload while the record isn't committed yet: once the commit succeeds
        # the row points at this file, so a later failure (e.g. on refresh) must keep it.
        try:
            meditation = await self._insert(payload)
        except BaseException:
            await self.db.rollback()
            try:
                await self.storage.delete(key)
            except Exception:
                logger.exception("Failed to delete orphaned meditation audio %s", key)
            raise

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

    async def update(
        self, meditation_id: uuid.UUID, payload: MeditationUpdate
    ) -> MeditationActivity:
        meditation = await self.get_by_id(meditation_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(meditation, field, value)

        await self.db.commit()
        await self.db.refresh(meditation)
        return meditation

    async def update_with_audio(
        self,
        meditation_id: uuid.UUID,
        payload: MeditationUpdate,
        audio: bytes | None,
    ) -> MeditationActivity:
        if audio is None:
            return await self.update(meditation_id, payload)
        if self.storage is None:
            raise RuntimeError("MeditationService needs an AudioStorage to upload audio")

        meditation = await self.get_by_id(meditation_id)
        old_key = audio_key_from_url(meditation.audio_url)

        new_key = build_audio_key()
        await self.storage.save(new_key, audio)

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(meditation, field, value)
        meditation.audio_url = build_audio_url(new_key)

        try:
            await self.db.commit()
        except BaseException:
            await self.db.rollback()
            await self._delete_audio_quietly(new_key)
            raise
        if old_key is not None:
            await self._delete_audio_quietly(old_key)

        await self.db.refresh(meditation)
        return meditation

    async def _delete_audio_quietly(self, key: str) -> None:
        if self.storage is None:
            return
        try:
            await self.storage.delete(key)
        except Exception:
            logger.exception("Failed to delete meditation audio %s", key)

    async def delete(self, meditation_id: uuid.UUID) -> None:
        meditation = await self.get_by_id(meditation_id)
        meditation.enabled = False
        meditation.deleted_at = datetime.now(UTC)
        await self.db.commit()
