from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.percentages import to_percentages
from app.enums import Gender, Role
from app.models.user import User

MINIMUM_AGE = 13

AGE_RANGES: list[tuple[str, int, int | None]] = [
    ("13-17", 13, 17),
    ("18-24", 18, 24),
    ("25-34", 25, 34),
    ("35-44", 35, 44),
    ("45-59", 45, 59),
    ("60+", 60, None),
]


def years_before(day: date, years: int) -> date:
    # 29/02 vira 28/02 quando o ano de destino não é bissexto.
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


def counted_users(today: date) -> tuple[ColumnElement[bool], ...]:
    # Usuários sem birth_date entram; menores de 13 e datas no futuro ficam de fora.
    latest_birth_date = years_before(today, MINIMUM_AGE)
    return (
        User.role == Role.USER,
        User.enabled.is_(True),
        User.deleted_at.is_(None),
        or_(User.birth_date.is_(None), User.birth_date <= latest_birth_date),
    )


def calculate_age(birth_date: date, today: date) -> int:
    had_birthday = (today.month, today.day) >= (birth_date.month, birth_date.day)
    return today.year - birth_date.year - (0 if had_birthday else 1)


def find_age_range(age: int) -> str | None:
    for label, minimum, maximum in AGE_RANGES:
        if age >= minimum and (maximum is None or age <= maximum):
            return label
    return None


class DashboardSummaryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_summary(self) -> dict[str, Any]:
        today = datetime.now(UTC).date()
        start_of_today = datetime.combine(today, time.min, tzinfo=UTC)
        counted = counted_users(today)

        total_users = await self.db.scalar(select(func.count()).select_from(User).where(*counted))
        premium_active_users = await self.db.scalar(
            select(func.count())
            .select_from(User)
            .where(*counted, User.plan_end_date >= start_of_today)
        )

        age_counts = {label: 0 for label, _, _ in AGE_RANGES}
        birth_dates = await self.db.scalars(select(User.birth_date).where(*counted))
        for birth_date in birth_dates:
            if birth_date is None:
                continue
            age_range = find_age_range(calculate_age(birth_date, today))
            if age_range is not None:
                age_counts[age_range] += 1

        gender_counts = dict.fromkeys(Gender, 0)
        gender_rows = await self.db.execute(
            select(User.gender, func.count()).where(*counted).group_by(User.gender)
        )
        for gender, count in gender_rows.all():
            gender_counts[gender] = count

        age_percentages = to_percentages(list(age_counts.values()))
        gender_percentages = to_percentages(list(gender_counts.values()))

        return {
            "total_users": total_users or 0,
            "premium_active_users": premium_active_users or 0,
            "age_distribution": [
                {"age_range": age_range, "count": count, "percentage": percentage}
                for (age_range, count), percentage in zip(
                    age_counts.items(), age_percentages, strict=True
                )
            ],
            "gender_distribution": [
                {"gender": gender, "count": count, "percentage": percentage}
                for (gender, count), percentage in zip(
                    gender_counts.items(), gender_percentages, strict=True
                )
            ],
        }
