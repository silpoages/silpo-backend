import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Mood
from app.models.achievement_log import AchievementLog
from app.models.diary_entry import DiaryEntry
from app.models.mood_log import MoodLog
from app.models.user import User
from app.schemas.diary_entry import DiaryEntryCreate, DiaryEntryRead
from app.services.diary_entry import DiaryEntryService
from app.services.image_storage import LocalImageStorage, new_image_key

CreateUser = Callable[..., Awaitable[User]]

DAY = date(2026, 11, 5)


def _payload(**overrides: object) -> DiaryEntryCreate:
    fields: dict[str, object] = {"note": "relato", "entry_date": DAY}
    fields.update(overrides)
    return DiaryEntryCreate.model_validate(fields)


async def _add_mood_log(
    db_session: AsyncSession, user: User, mood: Mood = Mood.BEM, log_date: date = DAY
) -> MoodLog:
    mood_log = MoodLog(user_id=user.id, mood=mood, log_date=log_date)
    db_session.add(mood_log)
    await db_session.commit()
    await db_session.refresh(mood_log)
    return mood_log


@pytest.mark.parametrize("note", ["", "   ", "\n\t"])
def test_blank_note_is_rejected(note: str) -> None:
    with pytest.raises(ValidationError):
        DiaryEntryCreate(note=note)


def test_note_is_trimmed_and_unknown_fields_are_rejected() -> None:
    assert DiaryEntryCreate(note="  oi  ").note == "oi"
    with pytest.raises(ValidationError):
        DiaryEntryCreate.model_validate({"note": "oi", "user_id": str(uuid.uuid4())})


def test_invalid_date_and_mood_log_id_are_rejected() -> None:
    with pytest.raises(ValidationError):
        DiaryEntryCreate.model_validate({"note": "oi", "entry_date": "2026-13-40"})
    with pytest.raises(ValidationError):
        DiaryEntryCreate.model_validate({"note": "oi", "mood_log_id": "not-a-uuid"})
    with pytest.raises(ValidationError):
        DiaryEntryCreate.model_validate(
            {"note": "oi", "mood": Mood.FELIZ, "mood_log_id": str(uuid.uuid4())}
        )


async def test_create_without_mood_log_has_no_mood_and_no_practice(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()

    entry = await DiaryEntryService(db_session).create(user.id, _payload())
    read = DiaryEntryRead.model_validate(entry)

    assert read.mood_log_id is None
    assert read.mood is None
    assert read.practice is None
    assert read.note == "relato"


async def test_create_with_mood_stores_it_on_the_chosen_date(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    chosen = date(2026, 3, 18)

    entry = await DiaryEntryService(db_session).create(
        user.id, _payload(entry_date=chosen, mood=Mood.ANSIOSO)
    )
    read = DiaryEntryRead.model_validate(entry)
    stored = await db_session.scalar(select(MoodLog).where(MoodLog.id == entry.mood_log_id))

    assert read.mood == Mood.ANSIOSO
    assert stored is not None
    assert stored.user_id == user.id
    assert stored.log_date == chosen
    assert stored.mood == Mood.ANSIOSO


async def test_create_rejects_an_image_the_user_does_not_own(
    db_session: AsyncSession, create_user: CreateUser, tmp_path: Path
) -> None:
    owner = await create_user()
    intruder = await create_user()
    storage = LocalImageStorage(tmp_path)
    foreign_key = new_image_key(owner.id, "jpg")
    await storage.save(foreign_key, b"\xff\xd8\xffimg", "image/jpeg")

    with pytest.raises(HTTPException) as exc:
        await DiaryEntryService(db_session, storage).create(
            intruder.id, _payload(image_url=foreign_key)
        )

    assert exc.value.status_code == 404


async def test_delete_removes_the_private_image(
    db_session: AsyncSession, create_user: CreateUser, tmp_path: Path
) -> None:
    user = await create_user()
    storage = LocalImageStorage(tmp_path)
    service = DiaryEntryService(db_session, storage)
    key = await service.save_image(user.id, b"\xff\xd8\xffimg", "jpg")
    entry = await service.create(user.id, _payload(image_url=key))

    await service.delete(user.id, entry.id)

    assert await storage.exists(key) is False


async def test_create_with_own_mood_log_exposes_its_mood(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    mood_log = await _add_mood_log(db_session, user, Mood.TRISTE)

    entry = await DiaryEntryService(db_session).create(user.id, _payload(mood_log_id=mood_log.id))
    read = DiaryEntryRead.model_validate(entry)

    assert read.mood_log_id == mood_log.id
    assert read.mood == Mood.TRISTE


async def test_cannot_link_mood_log_from_another_account(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    intruder = await create_user()
    foreign_mood_log = await _add_mood_log(db_session, owner)

    with pytest.raises(HTTPException) as exc:
        await DiaryEntryService(db_session).create(
            intruder.id, _payload(mood_log_id=foreign_mood_log.id)
        )

    assert exc.value.status_code == 404
    count = await db_session.scalar(
        select(func.count(DiaryEntry.id)).where(DiaryEntry.user_id == intruder.id)
    )
    assert count == 0


async def test_cannot_link_nonexistent_mood_log(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()

    with pytest.raises(HTTPException) as exc:
        await DiaryEntryService(db_session).create(user.id, _payload(mood_log_id=uuid.uuid4()))

    assert exc.value.status_code == 404


async def test_entry_date_defaults_to_today_and_differs_from_created_at(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    service = DiaryEntryService(db_session)

    today = await service.create(user.id, DiaryEntryCreate(note="hoje"))
    past = await service.create(user.id, _payload(entry_date=date(2025, 1, 10)))

    assert today.entry_date == datetime.now(UTC).date()
    assert past.entry_date == date(2025, 1, 10)
    # `created_at` é o instante do envio, independente do dia a que o relato se refere.
    assert past.created_at.date() != past.entry_date
    assert abs(datetime.now(UTC) - past.created_at) < timedelta(minutes=1)


async def test_multiple_entries_on_same_date_are_kept_newest_first(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    service = DiaryEntryService(db_session)
    first = await service.create(user.id, _payload(note="manhã"))
    second = await service.create(user.id, _payload(note="noite"))

    entries = await service.list_entries(user.id, DAY)

    assert [entry.id for entry in entries] == [second.id, first.id]


async def test_list_filters_by_date_and_orders_by_date_desc(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    service = DiaryEntryService(db_session)
    old = await service.create(user.id, _payload(entry_date=date(2026, 11, 1)))
    recent = await service.create(user.id, _payload(entry_date=date(2026, 11, 9)))

    everything = await service.list_entries(user.id)
    only_old = await service.list_entries(user.id, date(2026, 11, 1))
    empty_day = await service.list_entries(user.id, date(2026, 11, 2))

    assert [entry.id for entry in everything] == [recent.id, old.id]
    assert [entry.id for entry in only_old] == [old.id]
    assert empty_day == []


async def test_entries_never_leak_to_another_account(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    other = await create_user()
    service = DiaryEntryService(db_session)
    entry = await service.create(owner.id, _payload())

    assert await service.list_entries(other.id) == []
    assert await service.list_entries(other.id, DAY) == []
    assert (await service.get_month_summary(other.id, 2026, 11)).days == []
    with pytest.raises(HTTPException) as get_exc:
        await service.get_by_id(other.id, entry.id)
    with pytest.raises(HTTPException) as delete_exc:
        await service.delete(other.id, entry.id)

    assert get_exc.value.status_code == 404
    assert delete_exc.value.status_code == 404
    assert (await service.get_by_id(owner.id, entry.id)).deleted_at is None


async def test_mood_logs_never_leak_to_another_account(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    other = await create_user()
    await _add_mood_log(db_session, owner)

    assert await DiaryEntryService(db_session).list_mood_logs(other.id) == []


async def test_delete_is_logical_and_hides_entry_everywhere(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    service = DiaryEntryService(db_session)
    kept = await service.create(user.id, _payload(note="mantido"))
    removed = await service.create(user.id, _payload(note="removido"))

    await service.delete(user.id, removed.id)

    assert [entry.id for entry in await service.list_entries(user.id)] == [kept.id]
    assert [entry.id for entry in await service.list_entries(user.id, DAY)] == [kept.id]
    summary = await service.get_month_summary(user.id, 2026, 11)
    assert [(day.entry_date, day.entries_count) for day in summary.days] == [(DAY, 1)]
    with pytest.raises(HTTPException) as exc:
        await service.get_by_id(user.id, removed.id)
    assert exc.value.status_code == 404

    row = await db_session.scalar(select(DiaryEntry).where(DiaryEntry.id == removed.id))
    assert row is not None
    assert row.enabled is False
    assert row.deleted_at is not None


async def test_deleting_twice_returns_404(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    service = DiaryEntryService(db_session)
    entry = await service.create(user.id, _payload())
    await service.delete(user.id, entry.id)

    with pytest.raises(HTTPException) as exc:
        await service.delete(user.id, entry.id)

    assert exc.value.status_code == 404


async def test_deleting_entry_keeps_its_mood_log_visible_in_diary(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    service = DiaryEntryService(db_session)
    mood_log = await _add_mood_log(db_session, user, Mood.ANSIOSO)
    entry = await service.create(user.id, _payload(mood_log_id=mood_log.id))

    await service.delete(user.id, entry.id)

    assert [log.id for log in await service.list_mood_logs(user.id, DAY)] == [mood_log.id]


async def test_month_summary_counts_multiple_entries_per_day_within_month_only(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    service = DiaryEntryService(db_session)
    for entry_date in (
        date(2026, 11, 1),
        date(2026, 11, 15),
        date(2026, 11, 15),
        date(2026, 11, 30),
    ):
        await service.create(user.id, _payload(entry_date=entry_date))
    for outside in (date(2026, 10, 31), date(2026, 12, 1)):
        await service.create(user.id, _payload(entry_date=outside))

    summary = await service.get_month_summary(user.id, 2026, 11)

    assert (summary.year, summary.month) == (2026, 11)
    assert [(day.entry_date, day.entries_count) for day in summary.days] == [
        (date(2026, 11, 1), 1),
        (date(2026, 11, 15), 2),
        (date(2026, 11, 30), 1),
    ]


async def test_month_summary_marks_a_day_that_only_has_a_home_mood(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    service = DiaryEntryService(db_session)
    await _add_mood_log(db_session, user, Mood.FELIZ, date(2026, 11, 4))
    await _add_mood_log(db_session, user, Mood.BEM, date(2026, 11, 4))
    await service.create(user.id, _payload(entry_date=date(2026, 11, 5), mood=Mood.TRISTE))

    summary = await service.get_month_summary(user.id, 2026, 11)
    by_day = {day.entry_date: day for day in summary.days}

    assert by_day[date(2026, 11, 4)].entries_count == 0
    assert set(by_day[date(2026, 11, 4)].moods) == {Mood.FELIZ, Mood.BEM}
    assert by_day[date(2026, 11, 5)].entries_count == 1
    assert by_day[date(2026, 11, 5)].moods == [Mood.TRISTE]


async def test_month_summary_handles_empty_months_and_leap_february(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    service = DiaryEntryService(db_session)
    await service.create(user.id, _payload(entry_date=date(2028, 2, 29)))

    assert (await service.get_month_summary(user.id, 2026, 3)).days == []
    leap = await service.get_month_summary(user.id, 2028, 2)
    assert [day.entry_date for day in leap.days] == [date(2028, 2, 29)]


@pytest.mark.parametrize(("year", "month"), [(2026, 0), (2026, 13), (0, 5), (10000, 5)])
async def test_month_summary_rejects_invalid_period(
    db_session: AsyncSession, create_user: CreateUser, year: int, month: int
) -> None:
    user = await create_user()

    with pytest.raises(HTTPException) as exc:
        await DiaryEntryService(db_session).get_month_summary(user.id, year, month)

    assert exc.value.status_code == 422


async def test_home_mood_logs_are_listed_without_inventing_notes(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    service = DiaryEntryService(db_session)
    morning = await _add_mood_log(db_session, user, Mood.FELIZ)
    night = await _add_mood_log(db_session, user, Mood.CANSADO)
    await _add_mood_log(db_session, user, Mood.BEM, log_date=date(2026, 11, 6))

    on_day = await service.list_mood_logs(user.id, DAY)
    everything = await service.list_mood_logs(user.id)

    assert {log.id for log in on_day} == {morning.id, night.id}
    assert len(everything) == 3
    assert await service.list_entries(user.id) == []
    notes = await db_session.scalar(
        select(func.count(DiaryEntry.id)).where(DiaryEntry.user_id == user.id)
    )
    assert notes == 0


async def test_several_entries_can_share_the_same_mood_log(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    service = DiaryEntryService(db_session)
    mood_log = await _add_mood_log(db_session, user, Mood.IRRITADO)

    await service.create(user.id, _payload(note="a", mood_log_id=mood_log.id))
    await service.create(user.id, _payload(note="b", mood_log_id=mood_log.id))

    entries = await service.list_entries(user.id, DAY)
    assert {entry.mood for entry in entries} == {Mood.IRRITADO}
    assert len(entries) == 2


async def test_creating_entry_evaluates_achievements(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()
    before = await db_session.scalar(
        select(func.count(AchievementLog.id)).where(AchievementLog.user_id == user.id)
    )

    await DiaryEntryService(db_session).create(user.id, _payload())

    after = await db_session.scalar(
        select(func.count(AchievementLog.id)).where(AchievementLog.user_id == user.id)
    )
    assert before == 0
    assert after is not None
