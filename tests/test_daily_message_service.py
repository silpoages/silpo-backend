import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_message import DailyMessage
from app.schemas.daily_message import DailyMessageCreate, DailyMessageUpdate
from app.services.daily_message import DailyMessageService


async def _add(db_session: AsyncSession, text: str, **fields: Any) -> DailyMessage:
    daily_message = DailyMessage(message=text, **fields)
    db_session.add(daily_message)
    await db_session.commit()
    await db_session.refresh(daily_message)
    return daily_message


def test_create_strips_message() -> None:
    assert DailyMessageCreate(message="  oi  ").message == "oi"


def test_create_accepts_140_chars_with_surrounding_spaces() -> None:
    assert len(DailyMessageCreate(message=f" {'a' * 140} ").message) == 140


@pytest.mark.parametrize("value", ["", "   ", "a" * 141])
def test_create_rejects_invalid_message(value: str) -> None:
    with pytest.raises(ValidationError):
        DailyMessageCreate(message=value)


@pytest.mark.parametrize("value", ["", "   ", "a" * 141])
def test_update_rejects_invalid_message(value: str) -> None:
    with pytest.raises(ValidationError):
        DailyMessageUpdate(message=value)


def test_create_enabled_defaults_to_true() -> None:
    assert DailyMessageCreate(message="oi").enabled is True


async def test_create_persists_with_defaults(db_session: AsyncSession) -> None:
    created = await DailyMessageService(db_session).create(
        DailyMessageCreate(message="Respire fundo")
    )

    assert created.message == "Respire fundo"
    assert created.enabled is True
    assert created.last_shown is None


async def test_list_paginated_newest_first(db_session: AsyncSession) -> None:
    marker = uuid.uuid4().hex
    first = await _add(db_session, f"{marker} 1")
    second = await _add(db_session, f"{marker} 2")
    third = await _add(db_session, f"{marker} 3")
    service = DailyMessageService(db_session)

    page_1 = await service.list_paginated(1, 2, marker, None)
    page_2 = await service.list_paginated(2, 2, marker, None)

    assert [m.id for m in page_1] == [third.id, second.id]
    assert [m.id for m in page_2] == [first.id]


async def test_list_excludes_deleted_and_filters_by_enabled(db_session: AsyncSession) -> None:
    marker = uuid.uuid4().hex
    on = await _add(db_session, f"{marker} on")
    off = await _add(db_session, f"{marker} off", enabled=False)
    deleted = await _add(db_session, f"{marker} del", deleted_at=datetime.now(UTC))
    service = DailyMessageService(db_session)

    everything = await service.list_paginated(1, 10, marker, None)
    only_off = await service.list_paginated(1, 10, marker, False)

    assert {m.id for m in everything} == {on.id, off.id}
    assert deleted.id not in {m.id for m in everything}
    assert [m.id for m in only_off] == [off.id]


async def test_count_by_status(db_session: AsyncSession) -> None:
    marker = uuid.uuid4().hex
    await _add(db_session, f"{marker} a")
    await _add(db_session, f"{marker} b")
    await _add(db_session, f"{marker} c", enabled=False)
    await _add(db_session, f"{marker} d", deleted_at=datetime.now(UTC))

    counts = await DailyMessageService(db_session).count_by_status(marker)

    assert counts == {"total": 3, "enabled": 2, "disabled": 1}


async def test_update_changes_fields_and_keeps_last_shown(db_session: AsyncSession) -> None:
    shown = datetime(2026, 1, 1, tzinfo=UTC)
    existing = await _add(db_session, "antes", last_shown=shown)

    updated = await DailyMessageService(db_session).update(
        existing.id, DailyMessageUpdate(message="depois", enabled=False)
    )

    assert updated.message == "depois"
    assert updated.enabled is False
    assert updated.last_shown == shown


async def test_update_ignores_fields_not_sent(db_session: AsyncSession) -> None:
    existing = await _add(db_session, "igual", enabled=False)

    updated = await DailyMessageService(db_session).update(
        existing.id, DailyMessageUpdate(message="novo")
    )

    assert updated.message == "novo"
    assert updated.enabled is False


async def test_update_unknown_or_deleted_raises_404(db_session: AsyncSession) -> None:
    service = DailyMessageService(db_session)
    deleted = await _add(db_session, "apagada", deleted_at=datetime.now(UTC))

    for message_id in (uuid.uuid4(), deleted.id):
        with pytest.raises(HTTPException) as exc:
            await service.update(message_id, DailyMessageUpdate(message="x"))
        assert exc.value.status_code == 404
