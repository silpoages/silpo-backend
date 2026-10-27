from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import pwd_context
from app.models.password_reset_code import PasswordResetCode
from app.models.user import User
from app.services.password_reset import NUMERIC_CODE_MAX_FAILED_ATTEMPTS
from tests.conftest import extract_numeric_reset_code


def wrong_code(code: str) -> str:
    return f"{(int(code) + 1) % 1_000_000:06d}"


async def request_code(client: AsyncClient, email: str) -> None:
    response = await client.post("/auth/forgot-password", json={"email": email, "method": "CODE"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_forgot_password_with_code_method_emails_a_six_digit_code(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    mock_resend_send: MagicMock,
) -> None:
    user = await create_user()

    await request_code(client, user.email)

    payload = mock_resend_send.call_args[0][0]
    assert payload["to"] == [user.email]
    assert "reset-password?code=" not in payload["html"]
    assert len(extract_numeric_reset_code(mock_resend_send)) == 6


@pytest.mark.asyncio
async def test_forgot_password_with_code_method_for_unknown_email_sends_nothing(
    client: AsyncClient, mock_resend_send: MagicMock
) -> None:
    await request_code(client, "nobody@example.com")

    mock_resend_send.assert_not_called()


@pytest.mark.asyncio
async def test_reset_password_with_numeric_code(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    mock_resend_send: MagicMock,
) -> None:
    user = await create_user()
    await request_code(client, user.email)
    code = extract_numeric_reset_code(mock_resend_send)

    verify = await client.post(
        "/auth/reset-password-code/verify", json={"email": user.email, "code": code}
    )
    reset = await client.post(
        "/auth/reset-password-code",
        json={"email": user.email, "code": code, "new_password": "brand-new-password"},
    )
    reuse = await client.post(
        "/auth/reset-password-code",
        json={"email": user.email, "code": code, "new_password": "another-password"},
    )

    assert verify.status_code == 200
    assert reset.status_code == 200
    assert reuse.status_code == 400
    await db_session.refresh(user)
    assert pwd_context.verify("brand-new-password", user.password)


@pytest.mark.asyncio
async def test_numeric_code_only_works_with_its_own_email(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    mock_resend_send: MagicMock,
) -> None:
    owner = await create_user()
    other = await create_user()
    await request_code(client, owner.email)
    code = extract_numeric_reset_code(mock_resend_send)

    response = await client.post(
        "/auth/reset-password-code/verify", json={"email": other.email, "code": code}
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_numeric_code_is_burned_after_too_many_wrong_attempts(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    mock_resend_send: MagicMock,
) -> None:
    user = await create_user()
    await request_code(client, user.email)
    code = extract_numeric_reset_code(mock_resend_send)

    for _ in range(NUMERIC_CODE_MAX_FAILED_ATTEMPTS):
        response = await client.post(
            "/auth/reset-password-code/verify",
            json={"email": user.email, "code": wrong_code(code)},
        )
        assert response.status_code == 400

    response = await client.post(
        "/auth/reset-password-code/verify", json={"email": user.email, "code": code}
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_requesting_a_new_numeric_code_invalidates_the_previous_one(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    mock_resend_send: MagicMock,
) -> None:
    user = await create_user()
    await request_code(client, user.email)
    first_code = extract_numeric_reset_code(mock_resend_send)
    await request_code(client, user.email)
    second_code = extract_numeric_reset_code(mock_resend_send)

    first = await client.post(
        "/auth/reset-password-code/verify", json={"email": user.email, "code": first_code}
    )
    second = await client.post(
        "/auth/reset-password-code/verify", json={"email": user.email, "code": second_code}
    )

    if first_code != second_code:
        assert first.status_code == 400
    assert second.status_code == 200


@pytest.mark.asyncio
async def test_expired_numeric_code_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    mock_resend_send: MagicMock,
) -> None:
    user = await create_user()
    await request_code(client, user.email)
    code = extract_numeric_reset_code(mock_resend_send)
    reset_code = await db_session.scalar(
        select(PasswordResetCode).where(PasswordResetCode.user_id == user.id)
    )
    assert reset_code is not None
    reset_code.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()

    response = await client.post(
        "/auth/reset-password-code/verify", json={"email": user.email, "code": code}
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_numeric_code_is_not_accepted_by_the_link_endpoints(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    mock_resend_send: MagicMock,
) -> None:
    user = await create_user()
    await request_code(client, user.email)
    code = extract_numeric_reset_code(mock_resend_send)

    response = await client.get(f"/auth/reset-password/{code}")

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_numeric_code_must_have_six_digits(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/reset-password-code/verify", json={"email": "user@example.com", "code": "12ab"}
    )

    assert response.status_code == 422
