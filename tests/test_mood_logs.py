import uuid
from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
async def test_create_mood_log_success(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.post(
        "/mood-logs",
        headers=auth_headers(user.id),
        json={"mood": "TRISTE"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["mood"] == "TRISTE"
    assert body["user_id"] == str(user.id)
    assert "id" in body
    assert "posted_at" in body


@pytest.mark.asyncio
async def test_create_mood_log_without_auth_header(client: AsyncClient) -> None:
    response = await client.post("/mood-logs", json={"mood": "TRISTE"})

    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_mood_log_with_invalid_token(client: AsyncClient) -> None:
    response = await client.post(
        "/mood-logs",
        headers={"Authorization": "Bearer not-a-real-token"},
        json={"mood": "TRISTE"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_mood_log_with_invalid_mood(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.post(
        "/mood-logs",
        headers=auth_headers(user.id),
        json={"mood": "NAO_EXISTE"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_mood_log_with_ansioso(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.post(
        "/mood-logs",
        headers=auth_headers(user.id),
        json={"mood": "ANSIOSO"},
    )

    assert response.status_code == 201
    assert response.json()["mood"] == "ANSIOSO"


@pytest.mark.asyncio
async def test_create_mood_log_twice_same_day_conflicts(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    headers = auth_headers(user.id)

    first = await client.post("/mood-logs", headers=headers, json={"mood": "FELIZ"})
    assert first.status_code == 201

    second = await client.post("/mood-logs", headers=headers, json={"mood": "TRISTE"})
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_get_today_mood_log_when_none_logged(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.get("/mood-logs/today", headers=auth_headers(user.id))

    assert response.status_code == 200
    assert response.json() is None


@pytest.mark.asyncio
async def test_get_today_mood_log_after_creating(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    headers = auth_headers(user.id)

    created = await client.post("/mood-logs", headers=headers, json={"mood": "BEM"})
    assert created.status_code == 201

    response = await client.get("/mood-logs/today", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["mood"] == "BEM"
    assert body["id"] == created.json()["id"]
