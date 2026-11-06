import hashlib
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import pwd_context
from app.models.password_reset_code import PasswordResetCode
from app.models.user import User
from tests.conftest import extract_reset_code


@pytest.mark.asyncio
async def test_forgot_password_sends_email_with_reset_link(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    mock_resend_send: MagicMock,
) -> None:
    user = await create_user()

    response = await client.post("/auth/forgot-password", json={"email": user.email})

    assert response.status_code == 200
    mock_resend_send.assert_called_once()
    payload = mock_resend_send.call_args[0][0]
    assert payload["to"] == [user.email]
    assert "/reset-password?code=" in payload["html"]


@pytest.mark.asyncio
async def test_forgot_password_unknown_email_does_not_send_email(
    client: AsyncClient, mock_resend_send: MagicMock
) -> None:
    response = await client.post(
        "/auth/forgot-password", json={"email": "no-such-user@example.com"}
    )

    assert response.status_code == 200
    mock_resend_send.assert_not_called()


@pytest.mark.asyncio
async def test_forgot_password_response_is_the_same_for_known_and_unknown_email(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
) -> None:
    user = await create_user()

    known_response = await client.post("/auth/forgot-password", json={"email": user.email})
    unknown_response = await client.post(
        "/auth/forgot-password", json={"email": "no-such-user@example.com"}
    )

    assert known_response.status_code == unknown_response.status_code == 200
    assert known_response.json() == unknown_response.json()


@pytest.mark.asyncio
async def test_verify_reset_password_code_success(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    mock_resend_send: MagicMock,
) -> None:
    user = await create_user()
    await client.post("/auth/forgot-password", json={"email": user.email})
    code = extract_reset_code(mock_resend_send)

    response = await client.get(f"/auth/reset-password/{code}")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_verify_reset_password_code_invalid(client: AsyncClient) -> None:
    response = await client.get("/auth/reset-password/not-a-real-code")

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_verify_reset_password_code_does_not_consume_it(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    mock_resend_send: MagicMock,
) -> None:
    user = await create_user()
    await client.post("/auth/forgot-password", json={"email": user.email})
    code = extract_reset_code(mock_resend_send)

    first = await client.get(f"/auth/reset-password/{code}")
    second = await client.get(f"/auth/reset-password/{code}")

    assert first.status_code == 200
    assert second.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_success(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    mock_resend_send: MagicMock,
) -> None:
    user = await create_user(password=pwd_context.hash("old-password"))
    await client.post("/auth/forgot-password", json={"email": user.email})
    code = extract_reset_code(mock_resend_send)

    response = await client.post(
        f"/auth/reset-password/{code}", json={"new_password": "brand-new-password"}
    )

    assert response.status_code == 200

    login_with_new_password = await client.post(
        "/auth/login", json={"email": user.email, "password": "brand-new-password"}
    )
    assert login_with_new_password.status_code == 200

    login_with_old_password = await client.post(
        "/auth/login", json={"email": user.email, "password": "old-password"}
    )
    assert login_with_old_password.status_code == 401


@pytest.mark.asyncio
async def test_reset_password_code_cannot_be_reused(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    mock_resend_send: MagicMock,
) -> None:
    user = await create_user()
    await client.post("/auth/forgot-password", json={"email": user.email})
    code = extract_reset_code(mock_resend_send)

    first = await client.post(
        f"/auth/reset-password/{code}", json={"new_password": "first-new-password"}
    )
    second = await client.post(
        f"/auth/reset-password/{code}", json={"new_password": "second-new-password"}
    )

    assert first.status_code == 200
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_rejects_invalid_code(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/reset-password/not-a-real-code", json={"new_password": "brand-new-password"}
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_rejects_expired_code(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
) -> None:
    user = await create_user()
    code = "expired-code"
    reset_code = PasswordResetCode(
        user_id=user.id,
        code_hash=hashlib.sha256(code.encode()).hexdigest(),
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add(reset_code)
    await db_session.commit()

    response = await client.post(
        f"/auth/reset-password/{code}", json={"new_password": "brand-new-password"}
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_rejects_too_short_password(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    mock_resend_send: MagicMock,
) -> None:
    user = await create_user()
    await client.post("/auth/forgot-password", json={"email": user.email})
    code = extract_reset_code(mock_resend_send)

    response = await client.post(f"/auth/reset-password/{code}", json={"new_password": "short"})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_user_can_change_password_with_correct_current_password(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user(password=pwd_context.hash("old-password"))

    response = await client.patch(
        "/users",
        headers=auth_headers(user.id),
        json={
            "full_name": "Nome Teste",
            "birth_date": "2000-01-01",
            "gender": "PREFER_NOT_TO_SAY",
            "daily_reminder_enabled": True,
            "current_password": "old-password",
            "new_password": "brand-new-password",
        },
    )

    assert response.status_code == 200

    login_with_new_password = await client.post(
        "/auth/login", json={"email": user.email, "password": "brand-new-password"}
    )
    assert login_with_new_password.status_code == 200


@pytest.mark.asyncio
async def test_update_user_rejects_password_change_with_wrong_current_password(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user(password=pwd_context.hash("old-password"))

    response = await client.patch(
        "/users",
        headers=auth_headers(user.id),
        json={
            "full_name": "Nome Teste",
            "birth_date": "2000-01-01",
            "gender": "PREFER_NOT_TO_SAY",
            "daily_reminder_enabled": True,
            "current_password": "wrong-password",
            "new_password": "brand-new-password",
        },
    )

    assert response.status_code == 403

    login_with_old_password = await client.post(
        "/auth/login", json={"email": user.email, "password": "old-password"}
    )
    assert login_with_old_password.status_code == 200


@pytest.mark.asyncio
async def test_update_user_rejects_new_password_without_current_password(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.patch(
        "/users",
        headers=auth_headers(user.id),
        json={
            "full_name": "Nome Teste",
            "birth_date": "2000-01-01",
            "gender": "PREFER_NOT_TO_SAY",
            "daily_reminder_enabled": True,
            "new_password": "brand-new-password",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_user_without_password_fields_is_unaffected(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user(password=pwd_context.hash("unchanged-password"))

    response = await client.patch(
        "/users",
        headers=auth_headers(user.id),
        json={
            "full_name": "Nome Teste",
            "birth_date": "2000-01-01",
            "gender": "PREFER_NOT_TO_SAY",
            "daily_reminder_enabled": True,
        },
    )

    assert response.status_code == 200

    login_response = await client.post(
        "/auth/login", json={"email": user.email, "password": "unchanged-password"}
    )
    assert login_response.status_code == 200
