import hashlib
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
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


BROWSER_HEADERS = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}


@pytest.mark.asyncio
async def test_confirm_email_from_browser_shows_confirmed_page(
    client: AsyncClient, db_session: AsyncSession, mock_resend_send: MagicMock
) -> None:
    register_response = await client.post(
        "/auth/register",
        json={"email": "confirm-browser@example.com", "password": "correct-horse-battery"},
    )
    user_id = register_response.json()["id"]
    code = extract_confirmation_code(mock_resend_send)

    response = await client.get(f"/auth/confirm-email/{code}", headers=BROWSER_HEADERS)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "E-mail confirmado" in response.text

    user = await db_session.get(User, uuid.UUID(user_id))
    assert user is not None
    assert user.email_confirmed_at is not None


@pytest.mark.asyncio
async def test_confirm_email_from_browser_shows_invalid_page(client: AsyncClient) -> None:
    response = await client.get("/auth/confirm-email/not-a-real-code", headers=BROWSER_HEADERS)

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("text/html")
    assert "Link inválido" in response.text


@pytest.mark.asyncio
async def test_confirm_email_from_browser_twice_shows_invalid_page(
    client: AsyncClient, mock_resend_send: MagicMock
) -> None:
    await client.post(
        "/auth/register",
        json={"email": "confirm-browser-twice@example.com", "password": "correct-horse-battery"},
    )
    code = extract_confirmation_code(mock_resend_send)

    first = await client.get(f"/auth/confirm-email/{code}", headers=BROWSER_HEADERS)
    second = await client.get(f"/auth/confirm-email/{code}", headers=BROWSER_HEADERS)

    assert "E-mail confirmado" in first.text
    assert second.status_code == 400
    assert "Link inválido" in second.text


@pytest.mark.asyncio
async def test_resend_confirmation_sends_a_new_working_link(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    mock_resend_send: MagicMock,
) -> None:
    user = await create_user(email_confirmed_at=None)

    response = await client.post("/auth/resend-confirmation", json={"email": user.email})

    assert response.status_code == 200
    mock_resend_send.assert_called_once()
    assert mock_resend_send.call_args[0][0]["to"] == [user.email]
    code = extract_confirmation_code(mock_resend_send)
    confirm_response = await client.get(f"/auth/confirm-email/{code}")
    assert confirm_response.status_code == 200


@pytest.mark.asyncio
async def test_resend_confirmation_is_silent_for_unknown_or_confirmed_accounts(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    mock_resend_send: MagicMock,
) -> None:
    confirmed_user = await create_user()

    unknown = await client.post("/auth/resend-confirmation", json={"email": "nobody@example.com"})
    confirmed = await client.post("/auth/resend-confirmation", json={"email": confirmed_user.email})

    assert unknown.status_code == 200
    assert confirmed.status_code == 200
    assert unknown.json() == confirmed.json()
    mock_resend_send.assert_not_called()


@pytest.mark.asyncio
async def test_resend_confirmation_respects_the_cooldown(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    mock_resend_send: MagicMock,
) -> None:
    user = await create_user(email_confirmed_at=None)

    await client.post("/auth/resend-confirmation", json={"email": user.email})
    await client.post("/auth/resend-confirmation", json={"email": user.email})
    assert mock_resend_send.call_count == 1

    confirmation = await db_session.scalar(
        select(EmailConfirmationCode).where(EmailConfirmationCode.user_id == user.id)
    )
    assert confirmation is not None
    confirmation.created_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()

    await client.post("/auth/resend-confirmation", json={"email": user.email})
    assert mock_resend_send.call_count == 2
