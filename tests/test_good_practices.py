import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.good_practice import GoodPractice
from app.models.user import User


async def test_list_good_practices_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/good-practices")

    assert response.status_code == 401


async def test_list_good_practices_returns_empty_when_none_exist(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.get("/good-practices", headers=auth_headers(user.id))

    assert response.status_code == 200
    assert response.json() == {"items": []}


async def test_list_good_practices_excludes_disabled_and_deleted(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    enabled = GoodPractice(title="Respire fundo", description="Inspire e expire devagar")
    disabled = GoodPractice(title="Desativada", description="x", enabled=False)
    deleted = GoodPractice(title="Removida", description="x", deleted_at=datetime.now(UTC))
    db_session.add_all([enabled, disabled, deleted])
    await db_session.commit()

    response = await client.get("/good-practices", headers=auth_headers(user.id))

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [str(enabled.id)]


async def test_list_good_practices_daily_returns_single_stable_item(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    headers = auth_headers(user.id)

    first = GoodPractice(title="Primeira", description="x")
    second = GoodPractice(title="Segunda", description="x")
    db_session.add_all([first, second])
    await db_session.commit()

    response_a = await client.get("/good-practices", params={"daily": True}, headers=headers)
    response_b = await client.get("/good-practices", params={"daily": True}, headers=headers)

    assert response_a.status_code == 200
    items_a = response_a.json()["items"]
    items_b = response_b.json()["items"]
    assert len(items_a) == 1
    assert items_a == items_b
