import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.breathing_activity import BreathingActivity
from app.models.meditation_activity import MeditationActivity
from app.models.self_regulation_activity import SelfRegulationActivity
from app.schemas.activity import (
    ActivityConfigurationRead,
    BreathingActivityRead,
    MeditationActivityRead,
    SelfRegulationActivityRead,
)


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

    async def get_configuration(self, activity_id: uuid.UUID) -> ActivityConfigurationRead | None:
        # Load the concrete subclass in one query. session.get(Activity) only
        # fetches the parent row and then lazy-loads the child columns, which
        # raises MissingGreenlet under asyncio.
        breathing = await self._load_enabled(BreathingActivity, activity_id)
        if isinstance(breathing, BreathingActivity):
            return BreathingActivityRead(
                id=breathing.id,
                name=breathing.name,
                type="breathing",
                max_duration_seconds=breathing.max_duration_seconds,
                inhale_seconds=breathing.inhale_seconds,
                hold_seconds=breathing.hold_seconds,
                exhale_seconds=breathing.exhale_seconds,
                repeat_count=breathing.repeat_count,
            )

        meditation = await self._load_enabled(MeditationActivity, activity_id)
        if isinstance(meditation, MeditationActivity):
            return MeditationActivityRead(
                id=meditation.id,
                name=meditation.name,
                type="meditation",
                max_duration_seconds=meditation.max_duration_seconds,
                audio_url=meditation.audio_url,
            )

        self_regulation = await self._load_enabled(SelfRegulationActivity, activity_id)
        if isinstance(self_regulation, SelfRegulationActivity):
            return SelfRegulationActivityRead(
                id=self_regulation.id,
                name=self_regulation.name,
                type="self_regulation",
                max_duration_seconds=self_regulation.max_duration_seconds,
                bubble_spawn_interval_ms=self_regulation.bubble_spawn_interval_ms,
            )

        return None

    async def _load_enabled(
        self,
        model: type[BreathingActivity | MeditationActivity | SelfRegulationActivity],
        activity_id: uuid.UUID,
    ) -> Activity | None:
        result = await self.db.execute(select(model).where(model.id == activity_id))
        activity = result.scalar_one_or_none()
        if activity is None or not activity.enabled or activity.deleted_at is not None:
            return None
        return activity
