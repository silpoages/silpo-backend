import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ActivityType
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
        activity = await self.db.get(Activity, activity_id)
        if activity is None or not activity.enabled or activity.deleted_at is not None:
            return None

        if activity.type == ActivityType.BREATHING:
            breathing = await self.db.get(BreathingActivity, activity_id)
            if breathing is None:
                return None
            return BreathingActivityRead(
                id=activity.id,
                name=activity.name,
                type="breathing",
                max_duration_seconds=activity.max_duration_seconds,
                inhale_seconds=breathing.inhale_seconds,
                hold_seconds=breathing.hold_seconds,
                exhale_seconds=breathing.exhale_seconds,
                repeat_count=breathing.repeat_count,
            )

        if activity.type == ActivityType.MEDITATION:
            meditation = await self.db.get(MeditationActivity, activity_id)
            if meditation is None:
                return None
            return MeditationActivityRead(
                id=activity.id,
                name=activity.name,
                type="meditation",
                max_duration_seconds=activity.max_duration_seconds,
                audio_url=meditation.audio_url,
            )

        if activity.type == ActivityType.SELF_REGULATION:
            self_regulation = await self.db.get(SelfRegulationActivity, activity_id)
            if self_regulation is None:
                return None
            return SelfRegulationActivityRead(
                id=activity.id,
                name=activity.name,
                type="self_regulation",
                max_duration_seconds=activity.max_duration_seconds,
                bubble_spawn_interval_ms=self_regulation.bubble_spawn_interval_ms,
            )

        return None
