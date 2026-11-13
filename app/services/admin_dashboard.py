from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ActivityType, Role
from app.models.activity_session import ActivitySession
from app.models.diary_entry import DiaryEntry
from app.models.good_practice_log import GoodPracticeLog
from app.models.user import User
from app.schemas.admin_dashboard import DashboardActivityRead

DASHBOARD_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def _counted_users_filter() -> tuple[ColumnElement[bool], ...]:
    return (User.role == Role.USER, User.enabled.is_(True), User.deleted_at.is_(None))


class AdminDashboardService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_activity_summary(
        self, period_days: int, now: datetime | None = None
    ) -> list[DashboardActivityRead]:
        today = (now or datetime.now(UTC)).astimezone(DASHBOARD_TIMEZONE).date()
        start_date = today - timedelta(days=period_days - 1)
        end_date = today + timedelta(days=1)
        start_at = datetime.combine(start_date, time.min, tzinfo=DASHBOARD_TIMEZONE)
        end_at = datetime.combine(end_date, time.min, tzinfo=DASHBOARD_TIMEZONE)
        counted_users = _counted_users_filter()

        activity_result = await self.db.execute(
            select(ActivitySession.type, func.count(ActivitySession.id))
            .join(User, User.id == ActivitySession.user_id)
            .where(
                ActivitySession.posted_at >= start_at,
                ActivitySession.posted_at < end_at,
                *counted_users,
            )
            .group_by(ActivitySession.type)
        )

        good_practice_result = await self.db.execute(
            select(func.count(GoodPracticeLog.id))
            .join(User, User.id == GoodPracticeLog.user_id)
            .where(
                GoodPracticeLog.posted_at >= start_at,
                GoodPracticeLog.posted_at < end_at,
                *counted_users,
            )
        )

        diary_result = await self.db.execute(
            select(func.count(DiaryEntry.id))
            .join(User, User.id == DiaryEntry.user_id)
            .where(
                DiaryEntry.entry_date >= start_date,
                DiaryEntry.entry_date < end_date,
                DiaryEntry.enabled.is_(True),
                DiaryEntry.deleted_at.is_(None),
                *counted_users,
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
