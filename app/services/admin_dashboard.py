from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ActivityType
from app.models.activity import Activity
from app.models.activity_session import ActivitySession
from app.models.diary_entry import DiaryEntry
from app.models.good_practice import GoodPractice
from app.models.good_practice_log import GoodPracticeLog
from app.schemas.admin_dashboard import DashboardActivityRead


class AdminDashboardService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_activity_summary(
        self,
        period_days: int,
    ) -> list[DashboardActivityRead]:
        end_at = datetime.now(UTC)
        start_at = end_at - timedelta(days=period_days)

        activity_result = await self.db.execute(
            select(
                ActivitySession.type,
                func.count(ActivitySession.id),
            )
            .join(
                Activity,
                Activity.id == ActivitySession.activity_id,
            )
            .where(
                ActivitySession.posted_at >= start_at,
                ActivitySession.posted_at <= end_at,
                Activity.enabled.is_(True),
                Activity.deleted_at.is_(None),
            )
            .group_by(ActivitySession.type)
        )

        good_practice_result = await self.db.execute(
            select(func.count(GoodPracticeLog.id))
            .join(
                GoodPractice,
                GoodPractice.id == GoodPracticeLog.good_practice_id,
            )
            .where(
                GoodPracticeLog.posted_at >= start_at,
                GoodPracticeLog.posted_at <= end_at,
                GoodPractice.enabled.is_(True),
                GoodPractice.deleted_at.is_(None),
            )
        )

        diary_result = await self.db.execute(
            select(func.count(DiaryEntry.id)).where(
                DiaryEntry.created_at >= start_at,
                DiaryEntry.created_at <= end_at,
                DiaryEntry.enabled.is_(True),
                DiaryEntry.deleted_at.is_(None),
            )
        )

        categories = {
            "breathing": DashboardActivityRead(id="breathing", name="Respiração", executions=0),
            "diary": DashboardActivityRead(id="diary", name="Diário", executions=0),
            "meditation": DashboardActivityRead(id="meditation", name="Meditação", executions=0),
            "good_practice": DashboardActivityRead(
                id="good_practice", name="Práticas do bem", executions=0
            ),
            "self_regulation": DashboardActivityRead(
                id="self_regulation", name="Autorregulação", executions=0
            ),
        }

        activity_ids = {
            ActivityType.BREATHING: "breathing",
            ActivityType.MEDITATION: "meditation",
            ActivityType.SELF_REGULATION: "self_regulation",
        }
        for activity_type, executions in activity_result.all():
            category_id = activity_ids[activity_type]
            categories[category_id] = categories[category_id].model_copy(
                update={"executions": executions}
            )

        categories["good_practice"] = categories["good_practice"].model_copy(
            update={"executions": good_practice_result.scalar_one()}
        )
        categories["diary"] = categories["diary"].model_copy(
            update={"executions": diary_result.scalar_one()}
        )

        return sorted(
            categories.values(),
            key=lambda item: (-item.executions, item.name),
        )
