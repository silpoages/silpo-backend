import hashlib
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_confirmation_code import EmailConfirmationCode
from app.models.user import User
from tests.conftest import extract_confirmation_code


@pytest.mark.asyncio
async def test_register_sends_confirmation_email(
    client: AsyncClient, mock_resend_send: MagicMock
) -> None:
    response = await client.post(
        "/auth/register",
        json={"email": "confirm-me@example.com", "password": "correct-horse-battery"},
    )

    assert response.status_code == 201
    mock_resend_send.assert_called_once()
    payload = mock_resend_send.call_args[0][0]
    assert payload["to"] == ["confirm-me@example.com"]
    assert "/auth/confirm-email/" in payload["html"]


@pytest.mark.asyncio
async def test_confirm_email_success(
    client: AsyncClient, db_session: AsyncSession, mock_resend_send: MagicMock
) -> None:
    register_response = await client.post(
        "/auth/register",
        json={"email": "confirm-success@example.com", "password": "correct-horse-battery"},
    )
    user_id = register_response.json()["id"]
    code = extract_confirmation_code(mock_resend_send)

    response = await client.get(f"/auth/confirm-email/{code}")

    assert response.status_code == 200
    assert response.json() == {"message": "Email confirmed"}

    user = await db_session.get(User, uuid.UUID(user_id))
    assert user is not None
    assert user.email_confirmed_at is not None


@pytest.mark.asyncio
async def test_confirm_email_invalid_code(client: AsyncClient) -> None:
    response = await client.get("/auth/confirm-email/not-a-real-code")

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_confirm_email_already_used(client: AsyncClient, mock_resend_send: MagicMock) -> None:
    await client.post(
        "/auth/register",
        json={"email": "confirm-twice@example.com", "password": "correct-horse-battery"},
    )
    code = extract_confirmation_code(mock_resend_send)

    first = await client.get(f"/auth/confirm-email/{code}")
    second = await client.get(f"/auth/confirm-email/{code}")

    assert first.status_code == 200
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_confirm_email_expired_code(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
) -> None:
    user = await create_user()
    code = "expired-code"
    confirmation = EmailConfirmationCode(
        user_id=user.id,
        code_hash=hashlib.sha256(code.encode()).hexdigest(),
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add(confirmation)
    await db_session.commit()

    response = await client.get(f"/auth/confirm-email/{code}")

    assert response.status_code == 400
