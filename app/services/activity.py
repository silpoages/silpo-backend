import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.breath_activity import BreathActivity
from app.models.meditation_activity import MeditationActivity
from app.models.self_regulation_activity import SelfRegulationActivity
from app.schemas.activity import (
    ActivityRead,
    BreathingActivityRead,
    BreathingConfiguration,
    MeditationActivityRead,
    MeditationConfiguration,
    SelfRegulationActivityRead,
    SelfRegulationConfiguration,
)


class ActivityService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_configuration(self, activity_id: uuid.UUID) -> ActivityRead | None:
        activity = await self.db.get(Activity, activity_id)
        if activity is None or not activity.enabled or activity.deleted_at is not None:
            return None

        breathing = await self.db.get(BreathActivity, activity_id)
        if breathing is not None:
            return BreathingActivityRead(
                id=activity.id,
                name=activity.name,
                type="breathing",
                max_duration_seconds=activity.max_duration_seconds,
                breathing=BreathingConfiguration(
                    inhale_seconds=breathing.inhale_seconds,
                    hold_seconds=breathing.hold_seconds,
                    exhale_seconds=breathing.exhale_seconds,
                    repeat_count=breathing.repeat_count,
                ),
            )

        meditation = await self.db.get(MeditationActivity, activity_id)
        if meditation is not None:
            return MeditationActivityRead(
                id=activity.id,
                name=activity.name,
                type="meditation",
                max_duration_seconds=activity.max_duration_seconds,
                meditation=MeditationConfiguration(audio_url=meditation.audio_url),
            )

        self_regulation = await self.db.get(SelfRegulationActivity, activity_id)
        if self_regulation is not None:
            return SelfRegulationActivityRead(
                id=activity.id,
                name=activity.name,
                type="self_regulation",
                max_duration_seconds=activity.max_duration_seconds,
                self_regulation=SelfRegulationConfiguration(
                    bubble_spawn_interval_ms=self_regulation.bubble_spawn_interval_ms
                ),
            )

        return None