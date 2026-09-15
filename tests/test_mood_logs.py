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
