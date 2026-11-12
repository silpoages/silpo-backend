import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.achievement_catalog import ACHIEVEMENTS_BY_CODE
from app.enums import AchievementRule, Mood
from app.models.achievement import Achievement
from app.models.achievement_log import AchievementLog
from app.models.activity import Activity
from app.models.activity_session import ActivitySession
from app.models.breathing_activity import BreathingActivity
from app.models.diary_entry import DiaryEntry
from app.models.good_practice import GoodPractice
from app.models.good_practice_log import GoodPracticeLog
from app.models.meditation_activity import MeditationActivity
from app.models.mood_log import MoodLog
from app.models.self_regulation_session import BreathingSession, MeditationSession
from app.models.user import User
from app.services.achievement import AchievementService
from scripts.seed import ensure_default_achievements

CreateUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[[uuid.UUID], dict[str, str]]


def _id(code: str) -> uuid.UUID:
    return ACHIEVEMENTS_BY_CODE[code].id


# Práticas e atividades são globais e o banco é compartilhado: o que um teste cria aqui é
# removido ao final, para não aparecer nas listagens testadas em outros módulos.
_created_practice_ids: list[uuid.UUID] = []
_created_activity_ids: list[uuid.UUID] = []


@pytest_asyncio.fixture(autouse=True)
async def catalog(db_session: AsyncSession) -> AsyncIterator[None]:
    # As conquistas são globais: o catálogo fica commitado para o tracking enxergá-lo.
    await ensure_default_achievements(db_session)
    await db_session.commit()
    yield
    await db_session.rollback()
    practice_ids = list(_created_practice_ids)
    activity_ids = list(_created_activity_ids)
    _created_practice_ids.clear()
    _created_activity_ids.clear()
    if practice_ids:
        await db_session.execute(
            delete(GoodPracticeLog).where(GoodPracticeLog.good_practice_id.in_(practice_ids))
        )
    for session in await db_session.scalars(
        select(ActivitySession).where(ActivitySession.activity_id.in_(activity_ids))
    ):
        await db_session.delete(session)
    for model, ids in ((GoodPractice, practice_ids), (Activity, activity_ids)):
        for row in await db_session.scalars(select(model).where(model.id.in_(ids))):
            await db_session.delete(row)
    await db_session.commit()


async def _unlocked_codes(db_session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    ids = set(
        await db_session.scalars(
            select(AchievementLog.achievement_id).where(AchievementLog.user_id == user_id)
        )
    )
    return {code for code, definition in ACHIEVEMENTS_BY_CODE.items() if definition.id in ids}


async def _add_moods(
    db_session: AsyncSession, user_id: uuid.UUID, moods: list[Mood]
) -> list[MoodLog]:
    # Cada emoção num dia novo, depois do último já usado pelo usuário.
    last_day = await db_session.scalar(
        select(func.max(MoodLog.log_date)).where(MoodLog.user_id == user_id)
    )
    first_day = last_day + timedelta(days=1) if last_day else date(2026, 1, 1)
    logs = [
        MoodLog(user_id=user_id, mood=mood, log_date=first_day + timedelta(days=index))
        for index, mood in enumerate(moods)
    ]
    db_session.add_all(logs)
    await db_session.commit()
    return logs


async def _create_practices(db_session: AsyncSession, count: int) -> list[GoodPractice]:
    practices = [
        GoodPractice(title=f"Prática {uuid.uuid4()}", description="Faça algo bom.")
        for _ in range(count)
    ]
    db_session.add_all(practices)
    await db_session.commit()
    _created_practice_ids.extend(practice.id for practice in practices)
    return practices


async def _add_practice_logs(
    db_session: AsyncSession, user_id: uuid.UUID, practices: list[GoodPractice]
) -> None:
    now = datetime.now(UTC)
    db_session.add_all(
        GoodPracticeLog(user_id=user_id, good_practice_id=practice.id, posted_at=now)
        for practice in practices
    )
    await db_session.commit()


async def _create_activities(
    db_session: AsyncSession,
) -> tuple[BreathingActivity, MeditationActivity]:
    breathing = BreathingActivity(
        name="Respiração",
        max_duration_seconds=120,
        inhale_seconds=4,
        hold_seconds=4,
        exhale_seconds=4,
        repeat_count=4,
    )
    meditation = MeditationActivity(
        name=f"Meditação {uuid.uuid4()}", max_duration_seconds=300, audio_url="https://x.y/a"
    )
    db_session.add_all([breathing, meditation])
    await db_session.commit()
    _created_activity_ids.extend([breathing.id, meditation.id])
    return breathing, meditation


async def _add_sessions(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    *,
    breathing: BreathingActivity | None = None,
    meditation: MeditationActivity | None = None,
    count: int,
) -> None:
    now = datetime.now(UTC)
    if breathing is not None:
        sessions: list[Any] = [
            BreathingSession(
                user_id=user_id, activity_id=breathing.id, time_spent_seconds=60, posted_at=now
            )
            for _ in range(count)
        ]
    else:
        assert meditation is not None
        sessions = [
            MeditationSession(
                user_id=user_id, activity_id=meditation.id, time_spent_seconds=60, posted_at=now
            )
            for _ in range(count)
        ]
    db_session.add_all(sessions)
    await db_session.commit()


async def _add_diary_entries(
    db_session: AsyncSession, user_id: uuid.UUID, count: int, **overrides: Any
) -> list[DiaryEntry]:
    mood_logs = await _add_moods(db_session, user_id, [Mood.BEM] * count)
    entries = [
        DiaryEntry(
            user_id=user_id,
            mood_log_id=log.id,
            entry_date=log.log_date,
            note="texto privado",
            **overrides,
        )
        for log in mood_logs
    ]
    db_session.add_all(entries)
    await db_session.commit()
    return entries


# --- Emoções ---------------------------------------------------------------------------------


async def test_first_mood_log_via_api_unlocks_first_step(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    user = await create_user()

    response = await client.post(
        "/mood-logs", json={"mood": "FELIZ"}, headers=auth_headers(user.id)
    )

    assert response.status_code == 201
    assert response.json()["mood"] == "FELIZ"
    assert await _unlocked_codes(db_session, user.id) == {"first_step"}


async def test_seven_distinct_days_unlock_knowing_myself(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    service = AchievementService(db_session)

    await _add_moods(db_session, user.id, [Mood.BEM] * 6)
    await service.evaluate(user.id)
    assert "knowing_myself" not in await _unlocked_codes(db_session, user.id)

    db_session.add(MoodLog(user_id=user.id, mood=Mood.BEM, log_date=date(2027, 2, 1)))
    await db_session.commit()
    await service.evaluate(user.id)

    assert "knowing_myself" in await _unlocked_codes(db_session, user.id)
    progress = await service.get_progress(user.id)
    assert progress[AchievementRule.MOOD_DAYS] == 7


async def test_several_moods_on_the_same_day_count_as_one_date(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    same_day = date(2026, 5, 1)
    db_session.add_all(
        MoodLog(user_id=user.id, mood=mood, log_date=same_day)
        for mood in [Mood.BEM, Mood.TRISTE, Mood.FELIZ, Mood.BEM, Mood.ANSIOSO, Mood.BEM, Mood.BEM]
    )
    await db_session.commit()
    service = AchievementService(db_session)

    await service.evaluate(user.id)

    progress = await service.get_progress(user.id)
    assert progress[AchievementRule.MOOD_LOGS] == 7
    assert progress[AchievementRule.MOOD_DAYS] == 1
    unlocked = await _unlocked_codes(db_session, user.id)
    assert "knowing_myself" not in unlocked
    assert {"first_step", "all_emotions_matter"} <= unlocked


async def test_three_distinct_moods_unlock_all_emotions_matter(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    service = AchievementService(db_session)

    await _add_moods(db_session, user.id, [Mood.BEM, Mood.BEM, Mood.TRISTE, Mood.TRISTE])
    await service.evaluate(user.id)
    assert "all_emotions_matter" not in await _unlocked_codes(db_session, user.id)

    db_session.add(MoodLog(user_id=user.id, mood=Mood.ANSIOSO, log_date=date(2027, 3, 1)))
    await db_session.commit()
    await service.evaluate(user.id)

    assert "all_emotions_matter" in await _unlocked_codes(db_session, user.id)


# --- Práticas do Bem -------------------------------------------------------------------------


async def test_completing_a_practice_via_api_unlocks_small_victories(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    user = await create_user()
    (practice,) = await _create_practices(db_session, 1)

    response = await client.post(
        f"/good-practices/{practice.id}/complete", headers=auth_headers(user.id)
    )

    assert response.status_code == 201
    assert await _unlocked_codes(db_session, user.id) == {"small_victories"}


async def test_repeated_practice_counts_as_completed_but_not_as_different(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    (practice,) = await _create_practices(db_session, 1)
    await _add_practice_logs(db_session, user.id, [practice] * 5)

    await AchievementService(db_session).evaluate(user.id)

    unlocked = await _unlocked_codes(db_session, user.id)
    assert {"small_victories", "cultivating_good"} <= unlocked
    assert "exploring_possibilities" not in unlocked


async def test_three_different_practices_unlock_exploring_possibilities(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    practices = await _create_practices(db_session, 3)
    await _add_practice_logs(db_session, user.id, practices)

    await AchievementService(db_session).evaluate(user.id)

    unlocked = await _unlocked_codes(db_session, user.id)
    assert "exploring_possibilities" in unlocked
    assert "cultivating_good" not in unlocked


# --- Exercícios ------------------------------------------------------------------------------


async def test_breathing_session_via_api_unlocks_moment_to_breathe(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    user = await create_user()
    breathing, _ = await _create_activities(db_session)

    response = await client.post(
        f"/activities/{breathing.id}/sessions",
        json={"time_spent_seconds": 60},
        headers=auth_headers(user.id),
    )

    assert response.status_code == 201
    assert await _unlocked_codes(db_session, user.id) == {"moment_to_breathe"}


async def test_other_exercises_do_not_unlock_moment_to_breathe(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    _, meditation = await _create_activities(db_session)
    await _add_sessions(db_session, user.id, meditation=meditation, count=3)

    await AchievementService(db_session).evaluate(user.id)

    assert "moment_to_breathe" not in await _unlocked_codes(db_session, user.id)


async def test_ten_exercise_sessions_unlock_taking_care_of_me(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    breathing, meditation = await _create_activities(db_session)
    service = AchievementService(db_session)
    # Práticas do Bem não são exercícios.
    practices = await _create_practices(db_session, 5)
    await _add_practice_logs(db_session, user.id, practices)
    await _add_sessions(db_session, user.id, breathing=breathing, count=4)
    await _add_sessions(db_session, user.id, meditation=meditation, count=5)

    await service.evaluate(user.id)
    assert "taking_care_of_me" not in await _unlocked_codes(db_session, user.id)

    await _add_sessions(db_session, user.id, meditation=meditation, count=1)
    await service.evaluate(user.id)

    assert "taking_care_of_me" in await _unlocked_codes(db_session, user.id)


# --- Diário ----------------------------------------------------------------------------------


async def test_one_and_five_diary_entries_unlock_their_achievements(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    service = AchievementService(db_session)

    await _add_diary_entries(db_session, user.id, 1)
    await service.evaluate(user.id)
    unlocked = await _unlocked_codes(db_session, user.id)
    assert "my_story_matters" in unlocked
    assert "putting_into_words" not in unlocked

    await _add_diary_entries(db_session, user.id, 4)
    await service.evaluate(user.id)

    assert "putting_into_words" in await _unlocked_codes(db_session, user.id)


async def test_disabled_and_deleted_diary_entries_do_not_count(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    await _add_diary_entries(db_session, user.id, 1, enabled=False)
    await _add_diary_entries(db_session, user.id, 1, deleted_at=datetime.now(UTC))

    progress = await AchievementService(db_session).get_progress(user.id)

    assert progress[AchievementRule.DIARY_ENTRIES] == 0


@pytest.fixture
def captured_queries(db_session: AsyncSession) -> Iterator[list[str]]:
    statements: list[str] = []
    engine = db_session.bind.sync_engine

    def _before_cursor_execute(*args: Any) -> None:
        statements.append(args[2])

    event.listen(engine, "before_cursor_execute", _before_cursor_execute)
    yield statements
    event.remove(engine, "before_cursor_execute", _before_cursor_execute)


async def test_diary_progress_never_reads_private_content(
    db_session: AsyncSession, create_user: CreateUser, captured_queries: list[str]
) -> None:
    user = await create_user()
    await _add_diary_entries(db_session, user.id, 1)
    captured_queries.clear()

    await AchievementService(db_session).get_progress(user.id)

    diary_queries = [s for s in captured_queries if "diary_entry" in s]
    assert diary_queries
    for statement in diary_queries:
        assert "diary_entry.note" not in statement
        assert "diary_entry.image_url" not in statement


# --- Garantias gerais ------------------------------------------------------------------------


async def test_user_without_records_has_zero_progress_and_no_unlocks(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    service = AchievementService(db_session)

    assert set((await service.get_progress(user.id)).values()) == {0}
    assert await service.evaluate(user.id) == []


async def test_records_of_other_users_do_not_count(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    other = await create_user()
    await _add_moods(db_session, other.id, [Mood.BEM, Mood.TRISTE, Mood.FELIZ])

    await AchievementService(db_session).evaluate(user.id)

    assert await _unlocked_codes(db_session, user.id) == set()


async def test_evaluation_is_idempotent(db_session: AsyncSession, create_user: CreateUser) -> None:
    user = await create_user()
    await _add_moods(db_session, user.id, [Mood.BEM])
    service = AchievementService(db_session)

    assert await service.evaluate(user.id) == [_id("first_step")]
    assert await service.evaluate(user.id) == []

    total = await db_session.scalar(
        select(func.count(AchievementLog.id)).where(AchievementLog.user_id == user.id)
    )
    assert total == 1


async def test_concurrent_evaluations_unlock_only_once(
    database_url: str, db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    await _add_moods(db_session, user.id, [Mood.BEM])
    engine = create_async_engine(database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _evaluate() -> list[uuid.UUID]:
        async with session_maker() as session:
            return await AchievementService(session).evaluate(user.id)

    try:
        results = await asyncio.gather(*(_evaluate() for _ in range(5)))
    finally:
        await engine.dispose()

    assert sorted(len(result) for result in results) == [0, 0, 0, 0, 1]
    assert await _unlocked_codes(db_session, user.id) == {"first_step"}


async def test_unlock_is_kept_after_the_record_is_deleted(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    (entry,) = await _add_diary_entries(db_session, user.id, 1)
    service = AchievementService(db_session)
    await service.evaluate(user.id)

    entry.deleted_at = datetime.now(UTC)
    await db_session.commit()
    await service.evaluate(user.id)

    assert "my_story_matters" in await _unlocked_codes(db_session, user.id)


async def test_disabled_achievement_is_not_unlocked(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    await _add_moods(db_session, user.id, [Mood.BEM])
    first_step = await db_session.get(Achievement, _id("first_step"))
    assert first_step is not None
    first_step.enabled = False
    await db_session.commit()

    try:
        assert await AchievementService(db_session).evaluate(user.id) == []
    finally:
        first_step.enabled = True
        await db_session.commit()


async def test_live_unlocks_are_pending_acknowledgement(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    await _add_moods(db_session, user.id, [Mood.BEM])

    await AchievementService(db_session).evaluate(user.id)

    log = await db_session.scalar(select(AchievementLog).where(AchievementLog.user_id == user.id))
    assert log is not None
    assert log.achieved_at is not None
    assert log.acknowledged_at is None


async def test_backfill_unlocks_existing_records_without_pending_alerts(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    await _add_moods(db_session, user.id, [Mood.BEM, Mood.TRISTE, Mood.FELIZ])
    service = AchievementService(db_session)

    await service.backfill()
    await service.backfill()

    logs = list(
        await db_session.scalars(select(AchievementLog).where(AchievementLog.user_id == user.id))
    )
    assert {log.achievement_id for log in logs} == {_id("first_step"), _id("all_emotions_matter")}
    assert all(log.acknowledged_at is not None for log in logs)
    # A segunda execução não registra nada de novo para o usuário.
    assert len(logs) == 2


async def test_evaluation_failure_does_not_break_the_saved_action(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await create_user()

    async def _fail(*_: Any, **__: Any) -> AsyncIterator[None]:
        raise RuntimeError("boom")

    monkeypatch.setattr(AchievementService, "get_progress", _fail)

    response = await client.post("/mood-logs", json={"mood": "BEM"}, headers=auth_headers(user.id))

    assert response.status_code == 201
    assert response.json()["mood"] == "BEM"
    saved = await db_session.scalar(select(MoodLog).where(MoodLog.user_id == user.id))
    assert saved is not None
    assert await _unlocked_codes(db_session, user.id) == set()
