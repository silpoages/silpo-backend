import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Role
from app.models.daily_message import DailyMessage
from app.models.user import User

CreateUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[[uuid.UUID], dict[str, str]]

URL = "/daily-messages/today"


async def _add(db_session: AsyncSession, text: str, **fields: Any) -> DailyMessage:
    daily_message = DailyMessage(message=text, **fields)
    db_session.add(daily_message)
    await db_session.commit()
    await db_session.refresh(daily_message)
    return daily_message


async def _clear(db_session: AsyncSession) -> None:
    # O banco de testes é compartilhado: remove as mensagens criadas por outros testes.
    await db_session.execute(
        update(DailyMessage)
        .where(DailyMessage.deleted_at.is_(None))
        .values(deleted_at=datetime.now(UTC))
    )
    await db_session.commit()


async def _user_headers(create_user: CreateUser, auth_headers: AuthHeaders) -> dict[str, str]:
    user = await create_user()
    return auth_headers(user.id)


async def test_today_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(URL)

    assert response.status_code == 401


@pytest.mark.parametrize("role", [Role.USER, Role.PROFESSIONAL, Role.ADMIN])
async def test_today_available_for_any_authenticated_role(
    role: Role,
    client: AsyncClient,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    user = await create_user(role=role)

    response = await client.get(URL, headers=auth_headers(user.id))

    assert response.status_code == 200


async def test_today_returns_null_when_there_are_no_messages(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    await _clear(db_session)

    response = await client.get(URL, headers=await _user_headers(create_user, auth_headers))

    assert response.status_code == 200
    assert response.json() is None


async def test_today_ignores_disabled_and_deleted_messages(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    await _clear(db_session)
    await _add(db_session, "Desabilitada", enabled=False)
    await _add(db_session, "Excluida", deleted_at=datetime.now(UTC))
    headers = await _user_headers(create_user, auth_headers)

    response = await client.get(URL, headers=headers)

    assert response.status_code == 200
    assert response.json() is None

    enabled = await _add(db_session, "Habilitada")

    response = await client.get(URL, headers=headers)

    assert response.json()["id"] == str(enabled.id)


async def test_today_returns_same_message_on_repeated_calls(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    await _clear(db_session)
    for i in range(3):
        await _add(db_session, f"Mensagem {i}")
    headers = await _user_headers(create_user, auth_headers)

    first = await client.get(URL, headers=headers)
    second = await client.get(URL, headers=headers)

    assert first.status_code == 200
    assert first.json() == second.json()

    shown = await db_session.get(DailyMessage, uuid.UUID(first.json()["id"]))
    assert shown is not None
    await db_session.refresh(shown)
    assert shown.last_shown is not None
    assert shown.last_shown.date() == datetime.now(UTC).date()


async def test_today_keeps_message_already_shown_today(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    await _clear(db_session)
    await _add(db_session, "Nunca mostrada")
    shown_today = await _add(db_session, "Mostrada hoje", last_shown=datetime.now(UTC))

    response = await client.get(URL, headers=await _user_headers(create_user, auth_headers))

    assert response.json()["id"] == str(shown_today.id)


async def test_today_rotates_to_least_recently_shown_message(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    await _clear(db_session)
    now = datetime.now(UTC)
    await _add(db_session, "Mostrada ontem", last_shown=now - timedelta(days=1))
    oldest = await _add(db_session, "Mostrada anteontem", last_shown=now - timedelta(days=2))

    response = await client.get(URL, headers=await _user_headers(create_user, auth_headers))

    assert response.json()["id"] == str(oldest.id)


async def test_today_prefers_message_never_shown(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    await _clear(db_session)
    await _add(db_session, "Mostrada ontem", last_shown=datetime.now(UTC) - timedelta(days=1))
    never_shown = await _add(db_session, "Nunca mostrada")

    response = await client.get(URL, headers=await _user_headers(create_user, auth_headers))

    assert response.json()["id"] == str(never_shown.id)


async def test_today_returns_only_display_fields(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    await _clear(db_session)
    daily_message = await _add(db_session, "Respire fundo")

    response = await client.get(URL, headers=await _user_headers(create_user, auth_headers))

    assert response.json() == {"id": str(daily_message.id), "message": "Respire fundo"}
