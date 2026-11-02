import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Role
from app.models.daily_message import DailyMessage
from app.models.user import User

CreateUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[[uuid.UUID], dict[str, str]]

URL = "/admin/daily-messages"


async def _add(db_session: AsyncSession, text: str, **fields: Any) -> DailyMessage:
    daily_message = DailyMessage(message=text, **fields)
    db_session.add(daily_message)
    await db_session.commit()
    await db_session.refresh(daily_message)
    return daily_message


async def _admin_headers(create_user: CreateUser, auth_headers: AuthHeaders) -> dict[str, str]:
    admin = await create_user(role=Role.ADMIN)
    return auth_headers(admin.id)


async def _seed(db_session: AsyncSession, marker: str) -> None:
    for i in range(3):
        await _add(db_session, f"{marker} on {i}")
    for i in range(2):
        await _add(db_session, f"{marker} off {i}", enabled=False)
    await _add(db_session, f"{marker} del", deleted_at=datetime.now(UTC))


async def test_list_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(URL)

    assert response.status_code == 401


async def test_list_forbidden_for_non_admin(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders
) -> None:
    user = await create_user()

    response = await client.get(URL, headers=auth_headers(user.id))

    assert response.status_code == 403


async def test_list_returns_counters_and_excludes_deleted(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    marker = uuid.uuid4().hex
    await _seed(db_session, marker)
    headers = await _admin_headers(create_user, auth_headers)

    response = await client.get(URL, params={"search": marker}, headers=headers)

    body = response.json()
    assert response.status_code == 200
    assert (body["total"], body["enabled"], body["disabled"]) == (5, 3, 2)
    assert len(body["items"]) == 5
    assert all(item["last_shown"] is None for item in body["items"])


async def test_list_enabled_filter_does_not_change_counters(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    marker = uuid.uuid4().hex
    await _seed(db_session, marker)
    headers = await _admin_headers(create_user, auth_headers)

    response = await client.get(URL, params={"search": marker, "enabled": False}, headers=headers)

    body = response.json()
    assert len(body["items"]) == 2
    assert all(item["enabled"] is False for item in body["items"])
    assert (body["total"], body["enabled"], body["disabled"]) == (5, 3, 2)


async def test_list_paginates(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    marker = uuid.uuid4().hex
    await _seed(db_session, marker)
    headers = await _admin_headers(create_user, auth_headers)

    page_1 = await client.get(URL, params={"search": marker, "page_size": 2}, headers=headers)
    page_3 = await client.get(
        URL, params={"search": marker, "page_size": 2, "page": 3}, headers=headers
    )

    assert len(page_1.json()["items"]) == 2
    assert len(page_3.json()["items"]) == 1
    assert page_3.json()["page"] == 3
    assert page_3.json()["page_size"] == 2


async def test_list_search_is_case_insensitive(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    marker = uuid.uuid4().hex
    await _add(db_session, f"Bom Dia {marker}")
    headers = await _admin_headers(create_user, auth_headers)

    response = await client.get(URL, params={"search": marker.upper()}, headers=headers)

    assert len(response.json()["items"]) == 1


async def test_list_rejects_invalid_pagination(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders
) -> None:
    headers = await _admin_headers(create_user, auth_headers)

    assert (await client.get(URL, params={"page": 0}, headers=headers)).status_code == 422
    assert (await client.get(URL, params={"page_size": 101}, headers=headers)).status_code == 422


async def test_create_requires_authentication_and_admin(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders
) -> None:
    user = await create_user()

    anonymous = await client.post(URL, json={"message": "oi"})
    non_admin = await client.post(URL, json={"message": "oi"}, headers=auth_headers(user.id))

    assert anonymous.status_code == 401
    assert non_admin.status_code == 403


async def test_create_returns_201_with_defaults(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders
) -> None:
    headers = await _admin_headers(create_user, auth_headers)

    response = await client.post(URL, json={"message": "  Bom dia  "}, headers=headers)

    body = response.json()
    assert response.status_code == 201
    assert body["message"] == "Bom dia"
    assert body["enabled"] is True
    assert body["last_shown"] is None
    assert body["id"]


async def test_create_with_enabled_false(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders
) -> None:
    headers = await _admin_headers(create_user, auth_headers)

    response = await client.post(URL, json={"message": "oi", "enabled": False}, headers=headers)

    assert response.status_code == 201
    assert response.json()["enabled"] is False


@pytest.mark.parametrize(
    "payload", [{}, {"message": ""}, {"message": "   "}, {"message": "a" * 141}]
)
async def test_create_rejects_invalid_payload(
    client: AsyncClient,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
    payload: dict[str, str],
) -> None:
    headers = await _admin_headers(create_user, auth_headers)

    response = await client.post(URL, json=payload, headers=headers)

    assert response.status_code == 422


async def test_patch_updates_message_and_enabled(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    existing = await _add(db_session, "antes")
    headers = await _admin_headers(create_user, auth_headers)

    response = await client.patch(
        f"{URL}/{existing.id}", json={"message": "depois", "enabled": False}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["message"] == "depois"
    assert response.json()["enabled"] is False


async def test_patch_does_not_change_last_shown(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    shown = datetime(2026, 1, 1, tzinfo=UTC)
    existing = await _add(db_session, "antes", last_shown=shown)
    headers = await _admin_headers(create_user, auth_headers)

    response = await client.patch(f"{URL}/{existing.id}", json={"enabled": False}, headers=headers)

    assert response.status_code == 200
    await db_session.refresh(existing)
    assert existing.last_shown == shown


async def test_patch_unknown_or_deleted_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    deleted = await _add(db_session, "apagada", deleted_at=datetime.now(UTC))
    headers = await _admin_headers(create_user, auth_headers)

    unknown = await client.patch(f"{URL}/{uuid.uuid4()}", json={"message": "x"}, headers=headers)
    gone = await client.patch(f"{URL}/{deleted.id}", json={"message": "x"}, headers=headers)

    assert unknown.status_code == 404
    assert gone.status_code == 404


async def test_patch_forbidden_for_non_admin(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    existing = await _add(db_session, "antes")
    user = await create_user()

    response = await client.patch(
        f"{URL}/{existing.id}", json={"message": "x"}, headers=auth_headers(user.id)
    )

    assert response.status_code == 403
