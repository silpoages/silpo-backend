import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Role
from app.models.good_practice import GoodPractice
from app.models.user import User

URL = "/admin/good-practices"

CreateGoodPractice = Callable[..., Awaitable[GoodPractice]]


@pytest_asyncio.fixture
async def create_good_practice(
    db_session: AsyncSession,
) -> AsyncGenerator[CreateGoodPractice, None]:
    created_ids: list[uuid.UUID] = []

    async def _create(**overrides: Any) -> GoodPractice:
        defaults: dict[str, Any] = {
            "title": "Beber água",
            "description": "Beba um copo de água agora.",
        }
        defaults.update(overrides)
        good_practice = GoodPractice(**defaults)
        db_session.add(good_practice)
        await db_session.commit()
        await db_session.refresh(good_practice)
        created_ids.append(good_practice.id)
        return good_practice

    yield _create

    # Limpeza: apaga o que este teste criou, para não interferir nos outros arquivos de teste
    # (o banco de testes é compartilhado entre todos os testes da rodada).
    await db_session.execute(delete(GoodPractice).where(GoodPractice.id.in_(created_ids)))
    await db_session.commit()


async def test_list_admin_good_practices_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(URL)

    assert response.status_code == 401


async def test_list_admin_good_practices_forbidden_for_non_admin(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.get(URL, headers=auth_headers(user.id))

    assert response.status_code == 403


async def test_list_admin_good_practices_returns_paginated_shape(
    client: AsyncClient,
    create_good_practice: CreateGoodPractice,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    marker = uuid.uuid4().hex
    await create_good_practice(title=f"Prática {marker}")

    response = await client.get(URL, params={"search": marker}, headers=auth_headers(admin.id))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert set(body["items"][0]) == {"id", "title", "description", "enabled"}


async def test_list_admin_good_practices_includes_enabled_and_disabled_but_not_deleted(
    client: AsyncClient,
    create_good_practice: CreateGoodPractice,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    marker = uuid.uuid4().hex
    enabled = await create_good_practice(title=f"Habilitada {marker}")
    disabled = await create_good_practice(title=f"Desabilitada {marker}", enabled=False)
    deleted = await create_good_practice(title=f"Removida {marker}", deleted_at=datetime.now(UTC))

    response = await client.get(URL, params={"search": marker}, headers=auth_headers(admin.id))

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert ids == {str(enabled.id), str(disabled.id)}
    assert str(deleted.id) not in ids


async def test_list_admin_good_practices_filters_by_enabled(
    client: AsyncClient,
    create_good_practice: CreateGoodPractice,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    marker = uuid.uuid4().hex
    enabled = await create_good_practice(title=f"Habilitada {marker}")
    disabled = await create_good_practice(title=f"Desabilitada {marker}", enabled=False)
    headers = auth_headers(admin.id)

    only_disabled = await client.get(
        URL, params={"search": marker, "enabled": False}, headers=headers
    )
    only_enabled = await client.get(
        URL, params={"search": marker, "enabled": True}, headers=headers
    )

    assert [item["id"] for item in only_disabled.json()["items"]] == [str(disabled.id)]
    assert [item["id"] for item in only_enabled.json()["items"]] == [str(enabled.id)]


async def test_list_admin_good_practices_search_matches_title_or_description(
    client: AsyncClient,
    create_good_practice: CreateGoodPractice,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    marker = uuid.uuid4().hex
    in_title = await create_good_practice(title=f"Título {marker}")
    in_description = await create_good_practice(description=f"Descrição {marker.upper()}")
    other = await create_good_practice(title="Outra prática")

    response = await client.get(URL, params={"search": marker}, headers=auth_headers(admin.id))

    ids = {item["id"] for item in response.json()["items"]}
    assert ids == {str(in_title.id), str(in_description.id)}
    assert str(other.id) not in ids


async def test_list_admin_good_practices_paginates(
    client: AsyncClient,
    create_good_practice: CreateGoodPractice,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    marker = uuid.uuid4().hex
    for number in range(3):
        await create_good_practice(title=f"Item {number} {marker}")
    headers = auth_headers(admin.id)

    first_page = await client.get(
        URL, params={"search": marker, "page": 1, "page_size": 2}, headers=headers
    )
    second_page = await client.get(
        URL, params={"search": marker, "page": 2, "page_size": 2}, headers=headers
    )

    first_body = first_page.json()
    second_body = second_page.json()
    assert first_body["total"] == 3
    assert second_body["total"] == 3
    assert len(first_body["items"]) == 2
    assert len(second_body["items"]) == 1
    first_ids = {item["id"] for item in first_body["items"]}
    second_ids = {item["id"] for item in second_body["items"]}
    assert first_ids.isdisjoint(second_ids)


async def test_list_admin_good_practices_rejects_invalid_pagination(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    headers = auth_headers(admin.id)

    page_zero = await client.get(URL, params={"page": 0}, headers=headers)
    page_size_too_big = await client.get(URL, params={"page_size": 101}, headers=headers)

    assert page_zero.status_code == 422
    assert page_size_too_big.status_code == 422


async def test_mobile_list_does_not_expose_enabled(
    client: AsyncClient,
    create_good_practice: CreateGoodPractice,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    await create_good_practice()

    response = await client.get("/good-practices", headers=auth_headers(user.id))

    assert response.status_code == 200
    for item in response.json()["items"]:
        assert "enabled" not in item
