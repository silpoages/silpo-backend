import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Row, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.achievement import Achievement
from app.models.achievement_log import AchievementLog
from app.models.activity_session import ActivitySession
from app.models.good_practice_log import GoodPracticeLog
from app.models.mood_log import MoodLog
from app.schemas.journey import (
    JourneyAchievements,
    JourneyMoodCount,
    JourneyPeriod,
    JourneyRead,
    JourneySummary,
)


class JourneyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_current_month(self, user_id: uuid.UUID) -> JourneyRead:
        # Mesma referência UTC usada em MoodLog.log_date e nos posted_at dos logs.
        today = datetime.now(UTC).date()
        start_date = today.replace(day=1)
        next_month = (start_date + timedelta(days=32)).replace(day=1)
        end_date = next_month - timedelta(days=1)

        start = datetime.combine(start_date, time.min, tzinfo=UTC)
        end = datetime.combine(next_month, time.min, tzinfo=UTC)

        summary = await self._get_summary(user_id, start_date, next_month, start, end)
        mood_distribution = await self._get_mood_distribution(user_id, start_date, next_month)

        return JourneyRead(
            period=JourneyPeriod(
                month=start_date.strftime("%Y-%m"),
                start_date=start_date,
                end_date=end_date,
            ),
            summary=JourneySummary(
                mood_days=summary.mood_days,
                different_good_practices=summary.different_good_practices,
                completed_activities=summary.completed_activities,
            ),
            mood_distribution=mood_distribution,
            achievements=JourneyAchievements(
                unlocked=summary.unlocked_achievements,
                total=summary.total_achievements,
            ),
        )

    async def _get_summary(
        self,
        user_id: uuid.UUID,
        start_date: date,
        next_month: date,
        start: datetime,
        end: datetime,
    ) -> Row[Any]:
        # Todas as contagens em uma única ida ao banco via subqueries escalares.
        mood_days = (
            select(func.count(distinct(MoodLog.log_date)))
            .where(
                MoodLog.user_id == user_id,
                MoodLog.log_date >= start_date,
                MoodLog.log_date < next_month,
            )
            .scalar_subquery()
        )
        different_good_practices = (
            select(func.count(distinct(GoodPracticeLog.good_practice_id)))
            .where(
                GoodPracticeLog.user_id == user_id,
                GoodPracticeLog.posted_at >= start,
                GoodPracticeLog.posted_at < end,
            )
            .scalar_subquery()
        )
        completed_activities = (
            select(func.count(ActivitySession.id))
            .where(
                ActivitySession.user_id == user_id,
                ActivitySession.posted_at >= start,
                ActivitySession.posted_at < end,
            )
            .scalar_subquery()
        )
        available_achievement = (Achievement.enabled.is_(True), Achievement.deleted_at.is_(None))
        unlocked_achievements = (
            select(func.count(distinct(AchievementLog.achievement_id)))
            .join(Achievement, Achievement.id == AchievementLog.achievement_id)
            .where(AchievementLog.user_id == user_id, *available_achievement)
            .scalar_subquery()
        )
        total_achievements = (
            select(func.count(Achievement.id)).where(*available_achievement).scalar_subquery()
        )

        result = await self.db.execute(
            select(
                mood_days.label("mood_days"),
                different_good_practices.label("different_good_practices"),
                completed_activities.label("completed_activities"),
                unlocked_achievements.label("unlocked_achievements"),
                total_achievements.label("total_achievements"),
            )
        )
        return result.one()

    async def _get_mood_distribution(
        self, user_id: uuid.UUID, start_date: date, next_month: date
    ) -> list[JourneyMoodCount]:
        # GROUP BY só retorna emoções presentes, então contagens zero ficam de fora.
        count = func.count(MoodLog.id)
        result = await self.db.execute(
            select(MoodLog.mood, count)
            .where(
                MoodLog.user_id == user_id,
                MoodLog.log_date >= start_date,
                MoodLog.log_date < next_month,
            )
            .group_by(MoodLog.mood)
            .order_by(count.desc(), MoodLog.mood)
        )
        return [JourneyMoodCount(mood=mood, count=total) for mood, total in result.all()]
