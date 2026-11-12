import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Mood, Role
from app.models.mood_log import MoodLog
from app.models.user import User

URL = "/admin/dashboard/moods"


def _distribution(data: dict[str, Any]) -> dict[str, int]:
    return {item["mood"]: item["count"] for item in data["distribution"]}


def _day(data: dict[str, Any], day: str) -> dict[str, int]:
    return next(item["counts"] for item in data["daily"] if item["day"] == day)


async def test_moods_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(URL)

    assert response.status_code == 401


@pytest.mark.parametrize("role", [Role.USER, Role.PROFESSIONAL])
async def test_moods_forbidden_for_non_admin(
    role: Role,
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user(role=role)

    response = await client.get(URL, headers=auth_headers(user.id))

    assert response.status_code == 403


@pytest.mark.parametrize("period_days", ["0", "15", "365", "abc"])
async def test_moods_rejects_invalid_period(
    period_days: str,
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)

    response = await client.get(
        URL, params={"period_days": period_days}, headers=auth_headers(admin.id)
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("params", "expected_days"), [({}, 30), ({"period_days": 7}, 7), ({"period_days": 90}, 90)]
)
async def test_moods_returns_every_day_of_the_period(
    params: dict[str, int],
    expected_days: int,
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)

    response = await client.get(URL, params=params, headers=auth_headers(admin.id))

    assert response.status_code == 200
    data = response.json()
    today = datetime.now(UTC).date()
    expected = [(today - timedelta(days=offset)).isoformat() for offset in range(expected_days)]
    assert data["period_days"] == expected_days
    assert [item["day"] for item in data["daily"]] == expected[::-1]
    for item in data["daily"]:
        assert set(item["counts"]) == {mood.value for mood in Mood}


async def test_moods_returns_only_aggregated_data(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    user = await create_user()
    db_session.add(MoodLog(user_id=user.id, mood=Mood.BEM, log_date=datetime.now(UTC).date()))
    await db_session.commit()

    response = await client.get(URL, headers=auth_headers(admin.id))

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"period_days", "total_records", "daily", "distribution"}
    assert "user_id" not in response.text
    assert str(user.id) not in response.text
    assert sum(item["percentage"] for item in data["distribution"]) == pytest.approx(100)


async def test_moods_counts_records_in_period(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    headers = auth_headers(admin.id)
    params = {"period_days": 7}
    before = (await client.get(URL, params=params, headers=headers)).json()

    today = datetime.now(UTC).date()
    three_days_ago = today - timedelta(days=3)
    entries = [
        (Mood.FELIZ, today),
        (Mood.TRISTE, today),
        (Mood.FELIZ, three_days_ago),
        (Mood.ANSIOSO, today - timedelta(days=10)),
    ]
    for mood, log_date in entries:
        user = await create_user()
        db_session.add(MoodLog(user_id=user.id, mood=mood, log_date=log_date))
    await db_session.commit()

    response = await client.get(URL, params=params, headers=headers)

    assert response.status_code == 200
    after = response.json()
    assert after["total_records"] - before["total_records"] == 3

    before_distribution = _distribution(before)
    distribution_delta = {
        mood: count - before_distribution[mood] for mood, count in _distribution(after).items()
    }
    expected = {mood.value: 0 for mood in Mood}
    expected[Mood.FELIZ.value] = 2
    expected[Mood.TRISTE.value] = 1
    assert distribution_delta == expected

    day = three_days_ago.isoformat()
    before_day = _day(before, day)
    day_delta = {mood: count - before_day[mood] for mood, count in _day(after, day).items()}
    expected_day = {mood.value: 0 for mood in Mood}
    expected_day[Mood.FELIZ.value] = 1
    assert day_delta == expected_day


async def test_moods_ignore_disabled_and_deleted_users(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    headers = auth_headers(admin.id)
    params = {"period_days": 7}
    before = (await client.get(URL, params=params, headers=headers)).json()

    today = datetime.now(UTC).date()
    disabled = await create_user(enabled=False)
    deleted = await create_user(deleted_at=datetime.now(UTC))
    for user in (disabled, deleted):
        db_session.add(MoodLog(user_id=user.id, mood=Mood.TRISTE, log_date=today))
    await db_session.commit()

    response = await client.get(URL, params=params, headers=headers)

    assert response.status_code == 200
    after = response.json()
    assert after["total_records"] == before["total_records"]
    assert _distribution(after) == _distribution(before)
