import uuid
from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

CreateUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[[uuid.UUID], dict[str, str]]


@pytest.mark.parametrize("method", ["get", "patch"])
async def test_preferences_require_authentication(client: AsyncClient, method: str) -> None:
    response = await client.request(method, "/users/me/preferences")

    assert response.status_code == 401


async def test_reads_and_updates_only_the_daily_reminder(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    user = await create_user(full_name="Sol Andrade", onboarding_completed=False)
    other = await create_user(daily_reminder_enabled=True)

    current = await client.get("/users/me/preferences", headers=auth_headers(user.id))
    assert current.status_code == 200
    assert current.json() == {"daily_reminder_enabled": False}

    updated = await client.patch(
        "/users/me/preferences",
        headers=auth_headers(user.id),
        json={"daily_reminder_enabled": True},
    )
    assert updated.status_code == 200
    assert updated.json() == {"daily_reminder_enabled": True}

    await db_session.refresh(user)
    assert user.daily_reminder_enabled is True
    # Diferente do PATCH /users, não mexe no resto do cadastro nem conclui o onboarding.
    assert user.full_name == "Sol Andrade"
    assert user.onboarding_completed is False

    others = await client.get("/users/me/preferences", headers=auth_headers(other.id))
    assert others.json() == {"daily_reminder_enabled": True}


@pytest.mark.parametrize(
    "body",
    [{}, {"daily_reminder_enabled": "talvez"}, {"daily_reminder_enabled": True, "role": "ADMIN"}],
)
async def test_rejects_invalid_preferences(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders, body: dict
) -> None:
    user = await create_user()

    response = await client.patch("/users/me/preferences", headers=auth_headers(user.id), json=body)

    assert response.status_code == 422
