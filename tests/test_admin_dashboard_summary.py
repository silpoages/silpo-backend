import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.enums import Gender, Role
from app.models.user import User
from app.services.dashboard_summary import calculate_age, find_age_range, years_before

URL = "/admin/dashboard/summary"


def _years_ago(years: int) -> date:
    return date(datetime.now(UTC).year - years, 1, 1)


def _counts(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    return {item[key]: item["count"] for item in items}


def _delta(after: dict[str, int], before: dict[str, int]) -> dict[str, int]:
    return {key: after[key] - before[key] for key in after}


def test_calculate_age_before_and_after_birthday() -> None:
    assert calculate_age(date(2000, 6, 15), date(2026, 6, 14)) == 25
    assert calculate_age(date(2000, 6, 15), date(2026, 6, 15)) == 26


def test_find_age_range_limits() -> None:
    assert find_age_range(12) is None
    assert find_age_range(13) == "13-17"
    assert find_age_range(24) == "18-24"
    assert find_age_range(59) == "45-59"
    assert find_age_range(60) == "60+"


async def test_summary_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(URL)

    assert response.status_code == 401


@pytest.mark.parametrize("role", [Role.USER, Role.PROFESSIONAL])
async def test_summary_forbidden_for_non_admin(
    role: Role,
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user(role=role)

    response = await client.get(URL, headers=auth_headers(user.id))

    assert response.status_code == 403


async def test_summary_counts_only_active_users(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    headers = auth_headers(admin.id)
    before = (await client.get(URL, headers=headers)).json()

    future = datetime.now(UTC) + timedelta(days=30)
    past = datetime.now(UTC) - timedelta(days=1)
    await create_user(gender=Gender.FEMALE, birth_date=_years_ago(15), plan_end_date=future)
    await create_user(gender=Gender.MALE, birth_date=_years_ago(30), plan_end_date=past)
    await create_user(gender=Gender.MALE, birth_date=None)
    await create_user(gender=Gender.FEMALE, birth_date=_years_ago(70), enabled=False)
    await create_user(
        gender=Gender.FEMALE,
        birth_date=_years_ago(70),
        enabled=False,
        deleted_at=datetime.now(UTC),
        plan_end_date=future,
    )
    await create_user(
        role=Role.PROFESSIONAL,
        gender=Gender.OTHER,
        birth_date=_years_ago(40),
        plan_end_date=future,
    )

    response = await client.get(URL, headers=headers)

    assert response.status_code == 200
    after = response.json()
    assert after["total_users"] - before["total_users"] == 3
    assert after["premium_active_users"] - before["premium_active_users"] == 1

    age_delta = _delta(
        _counts(after["age_distribution"], "age_range"),
        _counts(before["age_distribution"], "age_range"),
    )
    assert age_delta == {"13-17": 1, "18-24": 0, "25-34": 1, "35-44": 0, "45-59": 0, "60+": 0}

    expected_genders = {gender.value: 0 for gender in Gender}
    expected_genders[Gender.MALE.value] = 2
    expected_genders[Gender.FEMALE.value] = 1
    gender_delta = _delta(
        _counts(after["gender_distribution"], "gender"),
        _counts(before["gender_distribution"], "gender"),
    )
    assert gender_delta == expected_genders


async def test_summary_returns_only_aggregated_data(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    user = await create_user(gender=Gender.FEMALE, birth_date=_years_ago(20))

    response = await client.get(URL, headers=auth_headers(admin.id))

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {
        "total_users",
        "premium_active_users",
        "age_distribution",
        "gender_distribution",
    }
    assert str(user.id) not in response.text
    assert user.email not in response.text
    assert sum(item["percentage"] for item in data["age_distribution"]) == pytest.approx(100)
    assert sum(item["percentage"] for item in data["gender_distribution"]) == pytest.approx(100)


def test_years_before_handles_leap_day() -> None:
    assert years_before(date(2026, 11, 12), 13) == date(2013, 11, 12)
    assert years_before(date(2028, 2, 29), 13) == date(2015, 2, 28)


async def test_summary_ignores_users_under_13_or_with_future_birth_date(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    headers = auth_headers(admin.id)
    before = (await client.get(URL, headers=headers)).json()

    today = datetime.now(UTC).date()
    future = datetime.now(UTC) + timedelta(days=30)
    await create_user(gender=Gender.FEMALE, birth_date=_years_ago(10), plan_end_date=future)
    await create_user(
        gender=Gender.MALE, birth_date=today + timedelta(days=30), plan_end_date=future
    )
    await create_user(gender=Gender.OTHER, birth_date=years_before(today, 13))

    response = await client.get(URL, headers=headers)

    assert response.status_code == 200
    after = response.json()
    assert after["total_users"] - before["total_users"] == 1
    assert after["premium_active_users"] == before["premium_active_users"]

    age_delta = _delta(
        _counts(after["age_distribution"], "age_range"),
        _counts(before["age_distribution"], "age_range"),
    )
    assert age_delta == {"13-17": 1, "18-24": 0, "25-34": 0, "35-44": 0, "45-59": 0, "60+": 0}

    expected_genders = {gender.value: 0 for gender in Gender}
    expected_genders[Gender.OTHER.value] = 1
    gender_delta = _delta(
        _counts(after["gender_distribution"], "gender"),
        _counts(before["gender_distribution"], "gender"),
    )
    assert gender_delta == expected_genders
