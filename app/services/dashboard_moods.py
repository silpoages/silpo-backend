from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.percentages import to_percentages
from app.enums import Mood
from app.models.mood_log import MoodLog
from app.models.user import User


class DashboardMoodsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_moods(self, period_days: int) -> dict[str, Any]:
        last_day = datetime.now(UTC).date()
        first_day = last_day - timedelta(days=period_days - 1)

        daily = {
            first_day + timedelta(days=offset): dict.fromkeys(Mood, 0)
            for offset in range(period_days)
        }
        totals = dict.fromkeys(Mood, 0)

        rows = await self.db.execute(
            select(MoodLog.log_date, MoodLog.mood, func.count())
            .join(User, User.id == MoodLog.user_id)
            .where(
                MoodLog.log_date >= first_day,
                MoodLog.log_date <= last_day,
                User.enabled.is_(True),
                User.deleted_at.is_(None),
            )
            .group_by(MoodLog.log_date, MoodLog.mood)
        )
        for log_date, mood, count in rows.all():
            daily[log_date][mood] = count
            totals[mood] += count

        percentages = to_percentages(list(totals.values()))

        return {
            "period_days": period_days,
            "total_records": sum(totals.values()),
            "daily": [{"day": day, "counts": counts} for day, counts in daily.items()],
            "distribution": [
                {"mood": mood, "count": count, "percentage": percentage}
                for (mood, count), percentage in zip(totals.items(), percentages, strict=True)
            ],
        }
