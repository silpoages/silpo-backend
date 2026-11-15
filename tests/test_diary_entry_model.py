import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Mood
from app.models.diary_entry import DiaryEntry
from app.models.mood_log import MoodLog
from app.models.user import User

CreateUser = Callable[..., Awaitable[User]]

DAY = date(2026, 11, 5)


async def _add_entry(db_session: AsyncSession, user: User, **overrides: Any) -> DiaryEntry:
    fields: dict[str, Any] = {"user_id": user.id, "entry_date": DAY, "note": "relato"}
    fields.update(overrides)
    entry = DiaryEntry(**fields)
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)
    return entry


async def test_user_can_have_multiple_entries_on_same_date(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    morning = await _add_entry(db_session, user, note="manhã")
    night = await _add_entry(db_session, user, note="noite")

    result = await db_session.execute(
        select(DiaryEntry.id).where(DiaryEntry.user_id == user.id, DiaryEntry.entry_date == DAY)
    )

    assert set(result.scalars().all()) == {morning.id, night.id}


async def test_entry_can_be_created_without_mood_log(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()

    entry = await _add_entry(db_session, user, note="sem check-in")

    assert entry.mood_log_id is None
    assert entry.image_url is None
    assert entry.enabled is True
    assert entry.deleted_at is None
    assert entry.created_at is not None


async def test_entry_can_be_linked_to_mood_log(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    mood_log = MoodLog(user_id=user.id, mood=Mood.BEM, log_date=DAY)
    db_session.add(mood_log)
    await db_session.commit()

    entry = await _add_entry(db_session, user, mood_log_id=mood_log.id)

    assert entry.mood_log_id == mood_log.id


async def test_mood_log_id_still_enforces_foreign_key(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    db_session.add(
        DiaryEntry(user_id=user.id, mood_log_id=uuid.uuid4(), entry_date=DAY, note="órfão")
    )

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize("missing", ["user_id", "entry_date", "note"])
async def test_required_columns_reject_null(
    db_session: AsyncSession, create_user: CreateUser, missing: str
) -> None:
    user = await create_user()
    fields: dict[str, Any] = {"user_id": user.id, "entry_date": DAY, "note": "relato"}
    fields[missing] = None
    db_session.add(DiaryEntry(**fields))

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_entries_are_isolated_by_user(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    other = await create_user()
    mine = await _add_entry(db_session, owner, note="meu")
    await _add_entry(db_session, other, note="de outra pessoa")

    result = await db_session.execute(select(DiaryEntry.id).where(DiaryEntry.user_id == owner.id))

    assert list(result.scalars().all()) == [mine.id]


async def test_calendar_query_filters_by_user_and_month(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    other = await create_user()
    in_november = [
        await _add_entry(db_session, user, entry_date=date(2026, 11, day)) for day in (1, 15, 30)
    ]
    await _add_entry(db_session, user, entry_date=date(2026, 10, 31))
    await _add_entry(db_session, user, entry_date=date(2026, 12, 1))
    await _add_entry(db_session, other, entry_date=date(2026, 11, 15))

    result = await db_session.execute(
        select(DiaryEntry.id).where(
            DiaryEntry.user_id == user.id,
            DiaryEntry.entry_date >= date(2026, 11, 1),
            DiaryEntry.entry_date < date(2026, 12, 1),
        )
    )

    assert set(result.scalars().all()) == {entry.id for entry in in_november}


async def test_soft_deleted_entry_stays_in_table_and_is_filtered_out(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    kept = await _add_entry(db_session, user, note="mantido")
    removed = await _add_entry(
        db_session, user, note="removido", enabled=False, deleted_at=datetime.now(UTC)
    )

    everything = await db_session.execute(
        select(DiaryEntry.id).where(DiaryEntry.user_id == user.id)
    )
    visible = await db_session.execute(
        select(DiaryEntry.id).where(
            DiaryEntry.user_id == user.id,
            DiaryEntry.enabled.is_(True),
            DiaryEntry.deleted_at.is_(None),
        )
    )

    assert set(everything.scalars().all()) == {kept.id, removed.id}
    assert list(visible.scalars().all()) == [kept.id]


async def test_schema_has_calendar_index_and_expected_nullability(
    db_session: AsyncSession,
) -> None:
    connection = await db_session.connection()
    indexes = await connection.run_sync(lambda conn: inspect(conn).get_indexes("diary_entry"))
    columns = await connection.run_sync(lambda conn: inspect(conn).get_columns("diary_entry"))

    indexed = {index["name"]: index["column_names"] for index in indexes}
    nullable = {column["name"]: column["nullable"] for column in columns}

    assert indexed["ix_diary_entry_user_id_entry_date"] == ["user_id", "entry_date"]
    assert nullable["entry_date"] is False
    assert nullable["mood_log_id"] is True
