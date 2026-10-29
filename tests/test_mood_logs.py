import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Mood
from app.models.mood_log import MoodLog
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


@pytest.mark.asyncio
async def test_list_mood_logs_with_optional_date_filter(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    other_user = await create_user()
    first = MoodLog(
        user_id=user.id,
        mood=Mood.FELIZ,
        log_date=date(2026, 9, 3),
        posted_at=datetime(2026, 9, 3, 12, 5, tzinfo=UTC),
    )
    second = MoodLog(
        user_id=user.id,
        mood=Mood.TRISTE,
        log_date=date(2026, 9, 4),
        posted_at=datetime(2026, 9, 4, 17, 42, tzinfo=UTC),
    )
    another_users_log = MoodLog(
        user_id=other_user.id,
        mood=Mood.CANSADO,
        log_date=date(2026, 9, 3),
        posted_at=datetime(2026, 9, 3, 18, 0, tzinfo=UTC),
    )
    db_session.add_all([first, second, another_users_log])
    await db_session.commit()

    all_response = await client.get("/mood-logs", headers=auth_headers(user.id))
    assert all_response.status_code == 200
    assert [item["id"] for item in all_response.json()["items"]] == [
        str(second.id),
        str(first.id),
    ]

    filtered_response = await client.get(
        "/mood-logs", params={"date": "2026-09-03"}, headers=auth_headers(user.id)
    )
    assert filtered_response.status_code == 200
    assert [item["id"] for item in filtered_response.json()["items"]] == [str(first.id)]


@pytest.mark.asyncio
async def test_list_mood_logs_rejects_invalid_date(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.get(
        "/mood-logs", params={"date": "not-a-date"}, headers=auth_headers(user.id)
    )

    assert response.status_code == 422
