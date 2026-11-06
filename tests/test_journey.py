import uuid
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Mood
from app.models.achievement import Achievement
from app.models.achievement_log import AchievementLog
from app.models.breathing_activity import BreathingActivity
from app.models.good_practice import GoodPractice
from app.models.good_practice_log import GoodPracticeLog
from app.models.mood_log import MoodLog
from app.models.self_regulation_session import BreathingSession
from app.models.user import User


def _month_start() -> datetime:
    now = datetime.now(UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC)


async def _total_available_achievements(db_session: AsyncSession) -> int:
    # Conquistas são globais e o banco é compartilhado entre testes.
    total = await db_session.scalar(
        select(func.count(Achievement.id)).where(
            Achievement.enabled.is_(True), Achievement.deleted_at.is_(None)
        )
    )
    return total or 0


async def _create_achievement(db_session: AsyncSession, **overrides: Any) -> Achievement:
    defaults: dict[str, Any] = {
        "name": "Primeiro passo",
        "image_url": "https://example.com/a.png",
        "description": "x",
    }
    defaults.update(overrides)
    achievement = Achievement(**defaults)
    db_session.add(achievement)
    await db_session.commit()
    await db_session.refresh(achievement)
    return achievement


async def _create_activity(db_session: AsyncSession) -> BreathingActivity:
    activity = BreathingActivity(
        name="Respiração", inhale_seconds=4, hold_seconds=4, exhale_seconds=4
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    return activity


async def _create_good_practice(db_session: AsyncSession) -> GoodPractice:
    good_practice = GoodPractice(title="Beber água", description="Beba um copo de água.")
    db_session.add(good_practice)
    await db_session.commit()
    await db_session.refresh(good_practice)
    return good_practice


@pytest.fixture
def captured_queries(db_session: AsyncSession) -> Iterator[list[str]]:
    statements: list[str] = []
    engine = db_session.bind.sync_engine

    def _before_cursor_execute(*args: Any) -> None:
        statements.append(args[2])

    event.listen(engine, "before_cursor_execute", _before_cursor_execute)
    yield statements
    event.remove(engine, "before_cursor_execute", _before_cursor_execute)


async def test_journey_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/journey")

    assert response.status_code == 401


async def test_journey_returns_zeroed_metrics_when_month_has_no_records(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    total_achievements = await _total_available_achievements(db_session)

    response = await client.get("/journey", headers=auth_headers(user.id))

    assert response.status_code == 200
    body = response.json()
    start = _month_start()
    next_month = (start + timedelta(days=32)).replace(day=1)
    assert body["period"] == {
        "month": start.strftime("%Y-%m"),
        "start_date": start.date().isoformat(),
        "end_date": (next_month - timedelta(days=1)).date().isoformat(),
    }
    assert body["summary"] == {
        "mood_days": 0,
        "different_good_practices": 0,
        "completed_activities": 0,
    }
    assert body["mood_distribution"] == []
    assert body["achievements"] == {"unlocked": 0, "total": total_achievements}


async def test_journey_aggregates_current_month_of_authenticated_user_only(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    other = await create_user()
    start = _month_start()
    previous_month = start - timedelta(days=1)

    for day, mood in enumerate([Mood.BEM, Mood.BEM, Mood.FELIZ]):
        db_session.add(
            MoodLog(user_id=user.id, mood=mood, log_date=start.date() + timedelta(days=day))
        )
    db_session.add(MoodLog(user_id=user.id, mood=Mood.TRISTE, log_date=previous_month.date()))
    db_session.add(MoodLog(user_id=other.id, mood=Mood.ANSIOSO, log_date=start.date()))

    practice_a = await _create_good_practice(db_session)
    practice_b = await _create_good_practice(db_session)
    db_session.add_all(
        [
            # Múltiplas conclusões da mesma prática contam como uma.
            GoodPracticeLog(user_id=user.id, good_practice_id=practice_a.id, posted_at=start),
            GoodPracticeLog(
                user_id=user.id,
                good_practice_id=practice_a.id,
                posted_at=start + timedelta(days=1),
            ),
            GoodPracticeLog(
                user_id=user.id, good_practice_id=practice_b.id, posted_at=previous_month
            ),
            GoodPracticeLog(user_id=other.id, good_practice_id=practice_b.id, posted_at=start),
        ]
    )

    activity = await _create_activity(db_session)
    db_session.add_all(
        [
            BreathingSession(
                user_id=user.id, activity_id=activity.id, time_spent_seconds=60, posted_at=start
            ),
            BreathingSession(
                user_id=user.id,
                activity_id=activity.id,
                time_spent_seconds=60,
                posted_at=start + timedelta(hours=1),
            ),
            BreathingSession(
                user_id=user.id,
                activity_id=activity.id,
                time_spent_seconds=60,
                posted_at=previous_month,
            ),
            BreathingSession(
                user_id=other.id, activity_id=activity.id, time_spent_seconds=60, posted_at=start
            ),
        ]
    )

    achievement = await _create_achievement(db_session)
    disabled = await _create_achievement(db_session, enabled=False)
    deleted = await _create_achievement(db_session, deleted_at=datetime.now(UTC))
    other_achievement = await _create_achievement(db_session)
    db_session.add_all(
        [
            AchievementLog(user_id=user.id, achievement_id=achievement.id),
            AchievementLog(user_id=user.id, achievement_id=achievement.id),
            AchievementLog(user_id=user.id, achievement_id=disabled.id),
            AchievementLog(user_id=user.id, achievement_id=deleted.id),
            AchievementLog(user_id=other.id, achievement_id=other_achievement.id),
        ]
    )
    await db_session.commit()
    total_achievements = await _total_available_achievements(db_session)

    response = await client.get("/journey", headers=auth_headers(user.id))

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "mood_days": 3,
        "different_good_practices": 1,
        "completed_activities": 2,
    }
    assert body["mood_distribution"] == [
        {"mood": "BEM", "count": 2},
        {"mood": "FELIZ", "count": 1},
    ]
    assert body["achievements"] == {"unlocked": 1, "total": total_achievements}


async def test_journey_ignores_user_id_in_query(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    other = await create_user()
    db_session.add(MoodLog(user_id=other.id, mood=Mood.BEM, log_date=_month_start().date()))
    await db_session.commit()

    response = await client.get(
        "/journey", params={"user_id": str(other.id)}, headers=auth_headers(user.id)
    )

    assert response.status_code == 200
    assert response.json()["summary"]["mood_days"] == 0
    assert response.json()["mood_distribution"] == []


async def test_journey_runs_fixed_number_of_queries_without_diary_entry(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
    captured_queries: list[str],
) -> None:
    user = await create_user()
    start = _month_start()
    for day in range(5):
        db_session.add(
            MoodLog(user_id=user.id, mood=Mood.BEM, log_date=start.date() + timedelta(days=day))
        )
    practice = await _create_good_practice(db_session)
    db_session.add_all(
        GoodPracticeLog(user_id=user.id, good_practice_id=practice.id, posted_at=start)
        for _ in range(5)
    )
    await db_session.commit()
    captured_queries.clear()

    response = await client.get("/journey", headers=auth_headers(user.id))

    assert response.status_code == 200
    # A busca do usuário autenticado pode vir do identity map; fora ela, só resumo + distribuição.
    journey_queries = [s for s in captured_queries if 'FROM "user"' not in s]
    assert len(journey_queries) == 2
    assert not any("diary_entry" in statement for statement in captured_queries)
