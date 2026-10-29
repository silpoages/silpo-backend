import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.security import pwd_context
from app.enums import Role
from app.models.user import User

EXPECTED_FIELDS = {"id", "email", "full_name", "role", "onboarding_completed"}


def _token_headers(payload: dict[str, object]) -> dict[str, str]:
    settings = get_settings()
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_me_returns_admin(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN, full_name="Administrador", onboarding_completed=True)

    response = await client.get("/auth/me", headers=auth_headers(admin.id))

    assert response.status_code == 200
    assert response.json() == {
        "id": str(admin.id),
        "email": admin.email,
        "full_name": "Administrador",
        "role": "ADMIN",
        "onboarding_completed": True,
    }


@pytest.mark.asyncio
async def test_me_returns_regular_user(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.get("/auth/me", headers=auth_headers(user.id))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == EXPECTED_FIELDS
    assert body["id"] == str(user.id)
    assert body["role"] == "USER"


@pytest.mark.asyncio
async def test_me_matches_login_user(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
) -> None:
    admin = await create_user(role=Role.ADMIN, password=pwd_context.hash("correct-password"))
    login = await client.post(
        "/auth/login", json={"email": admin.email, "password": "correct-password"}
    )
    token = login.json()["access_token"]

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == login.json()["user"]


@pytest.mark.asyncio
async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/auth/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_invalid_token(client: AsyncClient) -> None:
    response = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_expired_token(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
) -> None:
    user = await create_user()
    headers = _token_headers({"sub": str(user.id), "exp": datetime.now(UTC) - timedelta(minutes=1)})

    response = await client.get("/auth/me", headers=headers)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_disabled_account(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user(enabled=False)

    response = await client.get("/auth/me", headers=auth_headers(user.id))

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_deleted_account(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user(deleted_at=datetime.now(UTC))

    response = await client.get("/auth/me", headers=auth_headers(user.id))

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_endpoint_rejects_disabled_admin(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN, enabled=False)

    response = await client.get("/admin/users", headers=auth_headers(admin.id))

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_endpoint_rejects_invalid_token(client: AsyncClient) -> None:
    response = await client.get("/admin/users", headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_register_ignores_role_in_payload(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register",
        json={
            "email": f"{uuid.uuid4()}@example.com",
            "password": "correct-horse-battery",
            "role": "ADMIN",
        },
    )

    assert response.status_code == 201
    assert response.json()["role"] == "USER"
