import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.core.security import pwd_context
from app.enums import Role
from app.models.user import User


@pytest.mark.asyncio
async def test_login_success(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
) -> None:
    user = await create_user(password=pwd_context.hash("correct-password"))

    response = await client.post(
        "/auth/login", json={"email": user.email, "password": "correct-password"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["id"] == str(user.id)
    assert body["user"]["email"] == user.email


@pytest.mark.asyncio
async def test_login_wrong_password(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
) -> None:
    user = await create_user(password=pwd_context.hash("correct-password"))

    response = await client.post(
        "/auth/login", json={"email": user.email, "password": "wrong-password"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_disabled_user(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
) -> None:
    user = await create_user(password=pwd_context.hash("correct-password"), enabled=False)

    response = await client.post(
        "/auth/login", json={"email": user.email, "password": "correct-password"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_deleted_user(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
) -> None:
    user = await create_user(
        password=pwd_context.hash("correct-password"), deleted_at=datetime.now(UTC)
    )

    response = await client.post(
        "/auth/login", json={"email": user.email, "password": "correct-password"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_email_case_insensitive(
    client: AsyncClient, create_user: Callable[..., Awaitable[User]]
) -> None:
    # The stored email is already lowercase (as a correctly-normalized account would be) —
    # this checks that login normalizes the *input* before comparing, not the stored value.
    user = await create_user(
        email=f"{uuid.uuid4()}@example.com", password=pwd_context.hash("correct-password")
    )

    response = await client.post(
        "/auth/login",
        json={"email": user.email.upper(), "password": "correct-password"},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_self(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.delete(f"/users/{user.id}", headers=auth_headers(user.id))

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_other_user_as_admin(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    target = await create_user()

    response = await client.delete(f"/users/{target.id}", headers=auth_headers(admin.id))

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_other_user_as_non_admin_forbidden(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    other = await create_user()

    response = await client.delete(f"/users/{other.id}", headers=auth_headers(user.id))

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_unknown_user(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)

    response = await client.delete(f"/users/{uuid.uuid4()}", headers=auth_headers(admin.id))

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register",
        json={"email": "new-user@example.com", "password": "correct-horse-battery"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new-user@example.com"
    assert body["role"] == "USER"
    assert body["onboarding_completed"] is False
    assert "id" in body


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient) -> None:
    payload = {"email": "duplicate@example.com", "password": "correct-horse-battery"}

    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/auth/register", json=payload)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_register_password_too_short(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register", json={"email": "weak-password@example.com", "password": "short"}
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_then_login_with_mixed_case_email(client: AsyncClient) -> None:
    register_response = await client.post(
        "/auth/register",
        json={"email": "Mixed.Case@Example.com", "password": "correct-horse-battery"},
    )
    assert register_response.status_code == 201

    login_response = await client.post(
        "/auth/login",
        json={"email": "mixed.case@example.com", "password": "correct-horse-battery"},
    )
    assert login_response.status_code == 200
