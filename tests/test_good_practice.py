import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.good_practice import GoodPractice
from app.models.good_practice_log import GoodPracticeLog
from app.models.user import User


async def _create_good_practice(db_session: AsyncSession, **overrides: Any) -> GoodPractice:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "title": "Beber água",
        "description": "Beba um copo de água agora.",
    }
    defaults.update(overrides)
    good_practice = GoodPractice(**defaults)
    db_session.add(good_practice)
    await db_session.commit()
    await db_session.refresh(good_practice)
    return good_practice


@pytest.mark.asyncio
async def test_complete_good_practice_success(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    good_practice = await _create_good_practice(db_session)

    response = await client.post(
        f"/good-practices/{good_practice.id}/complete",
        headers=auth_headers(user.id),
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "good_practice_id", "completed_at"}
    assert body["good_practice_id"] == str(good_practice.id)

    result = await db_session.execute(
        select(GoodPracticeLog).where(GoodPracticeLog.id == uuid.UUID(body["id"]))
    )
    log = result.scalar_one()
    assert log.user_id == user.id
    assert log.good_practice_id == good_practice.id
    assert log.posted_at.tzinfo is not None
    assert log.posted_at <= datetime.now(UTC)


@pytest.mark.asyncio
async def test_complete_good_practice_can_be_repeated(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    good_practice = await _create_good_practice(db_session)
    url = f"/good-practices/{good_practice.id}/complete"

    first = await client.post(url, headers=auth_headers(user.id))
    second = await client.post(url, headers=auth_headers(user.id))

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.asyncio
async def test_complete_good_practice_not_found(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.post(
        f"/good-practices/{uuid.uuid4()}/complete",
        headers=auth_headers(user.id),
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_complete_good_practice_disabled(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    good_practice = await _create_good_practice(db_session, enabled=False)

    response = await client.post(
        f"/good-practices/{good_practice.id}/complete",
        headers=auth_headers(user.id),
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_complete_good_practice_deleted(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    good_practice = await _create_good_practice(db_session, deleted_at=datetime.now(UTC))

    response = await client.post(
        f"/good-practices/{good_practice.id}/complete",
        headers=auth_headers(user.id),
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_complete_good_practice_invalid_id(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.post(
        "/good-practices/not-a-uuid/complete",
        headers=auth_headers(user.id),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_complete_good_practice_without_auth_header(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    good_practice = await _create_good_practice(db_session)

    response = await client.post(f"/good-practices/{good_practice.id}/complete")

    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_complete_good_practice_with_invalid_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    good_practice = await _create_good_practice(db_session)

    response = await client.post(
        f"/good-practices/{good_practice.id}/complete",
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_complete_good_practice_with_unknown_user(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    good_practice = await _create_good_practice(db_session)

    response = await client.post(
        f"/good-practices/{good_practice.id}/complete",
        headers=auth_headers(uuid.uuid4()),
    )

    assert response.status_code == 401
