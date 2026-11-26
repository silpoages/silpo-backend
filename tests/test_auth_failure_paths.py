import logging
import uuid
from collections.abc import Awaitable, Callable, Iterator
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.email_confirmation_code import EmailConfirmationCode
from app.models.password_reset_code import PasswordResetCode
from app.models.user import User
from app.services.user import UserService
from tests.conftest import (
    extract_confirmation_code,
    extract_numeric_reset_code,
    extract_reset_code,
)

CreateUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[[uuid.UUID], dict[str, str]]


def _token(payload: dict[str, Any]) -> dict[str, str]:
    settings = get_settings()
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


def _hide_users(monkeypatch: pytest.MonkeyPatch, session: AsyncSession) -> None:
    """Simula a conta removida entre a leitura do código e a do usuário.

    Pelo banco isso não acontece de forma determinística (o código é apagado em cascata
    junto com o usuário), então o teste intercepta só a busca do usuário.
    """
    original_get = session.get

    async def get(entity: Any, ident: Any, **kwargs: Any) -> Any:
        if entity is User:
            return None
        return await original_get(entity, ident, **kwargs)

    monkeypatch.setattr(session, "get", get)


@pytest.fixture
def app_logs(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> Iterator[pytest.LogCaptureFixture]:
    """caplog com os loggers do app ligados.

    O fileConfig do Alembic (rodado pela fixture de migrações) desliga os loggers que já
    existiam, então sem isso nada do app chega ao caplog.
    """
    for name in ("app.services.email_confirmation", "app.services.password_reset"):
        monkeypatch.setattr(logging.getLogger(name), "disabled", False)
    with caplog.at_level(logging.ERROR):
        yield caplog


# --- token -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [{}, {"sub": "not-a-uuid"}, {"sub": ""}],
    ids=["no-subject", "subject-not-uuid", "empty-subject"],
)
async def test_token_without_a_valid_user_id_is_rejected(
    client: AsyncClient, payload: dict[str, Any]
) -> None:
    response = await client.get("/auth/me", headers=_token(payload))

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_token_signed_with_another_key_is_rejected(
    client: AsyncClient, create_user: CreateUser
) -> None:
    user = await create_user()
    token = jwt.encode({"sub": str(user.id)}, "another-secret-key-of-32-bytes!!", "HS256")

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_token_for_unknown_user_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/auth/me", headers=_token({"sub": str(uuid.uuid4())}))

    assert response.status_code == 401


# --- confirmação de e-mail ---------------------------------------------------------------


async def test_register_succeeds_and_keeps_the_code_when_the_email_provider_fails(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_resend_send: MagicMock,
    app_logs: pytest.LogCaptureFixture,
) -> None:
    mock_resend_send.side_effect = RuntimeError("provider down")
    email = f"{uuid.uuid4()}@example.com"

    response = await client.post(
        "/auth/register", json={"email": email, "password": "correct-horse-battery"}
    )

    assert response.status_code == 201
    user = await db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    assert user.email_confirmed_at is None
    codes = await db_session.scalars(
        select(EmailConfirmationCode).where(EmailConfirmationCode.user_id == user.id)
    )
    assert len(codes.all()) == 1
    assert f"Failed to send confirmation email to {email}" in app_logs.text


async def test_resend_after_a_failed_send_delivers_a_working_link(
    client: AsyncClient, db_session: AsyncSession, mock_resend_send: MagicMock
) -> None:
    email = f"{uuid.uuid4()}@example.com"
    mock_resend_send.side_effect = RuntimeError("provider down")
    await client.post("/auth/register", json={"email": email, "password": "correct-horse-battery"})
    # O código da primeira tentativa tem mais de 30 s para a regra de reenvio liberar.
    user = await db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    await db_session.execute(
        update(EmailConfirmationCode)
        .where(EmailConfirmationCode.user_id == user.id)
        .values(created_at=EmailConfirmationCode.created_at - timedelta(minutes=1))
    )
    await db_session.commit()
    mock_resend_send.side_effect = None
    mock_resend_send.reset_mock()

    resend = await client.post("/auth/resend-confirmation", json={"email": email})
    code = extract_confirmation_code(mock_resend_send)
    confirm = await client.get(f"/auth/confirm-email/{code}")

    assert resend.status_code == 200
    assert confirm.status_code == 200


async def test_confirm_email_rejects_code_whose_user_no_longer_exists(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_resend_send: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = f"{uuid.uuid4()}@example.com"
    await client.post("/auth/register", json={"email": email, "password": "correct-horse-battery"})
    code = extract_confirmation_code(mock_resend_send)
    _hide_users(monkeypatch, db_session)

    response = await client.get(f"/auth/confirm-email/{code}")

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid or expired confirmation code"}


# --- redefinição de senha ----------------------------------------------------------------


@pytest.mark.parametrize("method", ["LINK", "CODE"])
async def test_forgot_password_answers_200_and_keeps_the_code_when_the_provider_fails(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    mock_resend_send: MagicMock,
    app_logs: pytest.LogCaptureFixture,
    method: str,
) -> None:
    user = await create_user()
    mock_resend_send.side_effect = RuntimeError("provider down")

    response = await client.post(
        "/auth/forgot-password", json={"email": user.email, "method": method}
    )

    # Mesma resposta de um e-mail desconhecido: a falha não revela que a conta existe.
    assert response.status_code == 200
    assert response.json() == {"message": "If this email is registered, a reset link has been sent"}
    codes = await db_session.scalars(
        select(PasswordResetCode).where(PasswordResetCode.user_id == user.id)
    )
    assert len(codes.all()) == 1
    assert f"Failed to send password reset email to {user.email}" in app_logs.text


@pytest.mark.parametrize("path", ["/auth/reset-password-code/verify", "/auth/reset-password-code"])
async def test_numeric_code_for_unknown_email_is_rejected(client: AsyncClient, path: str) -> None:
    response = await client.post(
        path,
        json={"email": "nobody@example.com", "code": "123456", "new_password": "new-password-1"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid or expired reset code"}


async def test_numeric_code_of_a_disabled_account_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    mock_resend_send: MagicMock,
) -> None:
    user = await create_user()
    await client.post("/auth/forgot-password", json={"email": user.email, "method": "CODE"})
    code = extract_numeric_reset_code(mock_resend_send)
    user.enabled = False
    await db_session.commit()

    response = await client.post(
        "/auth/reset-password-code",
        json={"email": user.email, "code": code, "new_password": "new-password-1"},
    )

    assert response.status_code == 400
    await db_session.refresh(user)
    assert user.password == "hashed-password"


async def test_reset_password_rejects_code_whose_user_no_longer_exists(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    mock_resend_send: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await create_user()
    await client.post("/auth/forgot-password", json={"email": user.email})
    code = extract_reset_code(mock_resend_send)
    _hide_users(monkeypatch, db_session)

    response = await client.post(
        f"/auth/reset-password/{code}", json={"new_password": "new-password-1"}
    )

    assert response.status_code == 400
    reset_code = await db_session.scalar(
        select(PasswordResetCode).where(PasswordResetCode.user_id == user.id)
    )
    assert reset_code is not None
    assert reset_code.used_at is None


# --- UserService -------------------------------------------------------------------------


async def test_update_user_raises_for_unknown_user(db_session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="User not found"):
        await UserService(db_session).update_user(uuid.uuid4(), {"full_name": "Ninguém"})


async def test_conflict_on_another_unique_column_is_not_reported_as_duplicate_email(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    phone = f"+55{uuid.uuid4().int % 10**11:011d}"
    await create_user(phone_number=phone)
    other = await create_user()
    other_id = other.id
    admin = await create_user()

    with pytest.raises(IntegrityError, match="phone_number"):
        await UserService(db_session).update_by_admin(other_id, {"phone_number": phone}, admin)

    # A sessão continua utilizável depois do rollback, e nada foi gravado.
    reloaded = await db_session.get(User, other_id)
    assert reloaded is not None
    assert reloaded.phone_number is None


async def test_integrity_error_without_driver_error_is_raised_unchanged(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = IntegrityError("INSERT ...", None, None)  # type: ignore[arg-type]
    error.orig = None  # type: ignore[assignment]

    async def failing_commit() -> None:
        raise error

    monkeypatch.setattr(db_session, "commit", failing_commit)

    with pytest.raises(IntegrityError) as exc_info:
        await UserService(db_session).register(
            f"{uuid.uuid4()}@example.com", "correct-horse-battery"
        )

    assert exc_info.value is error


async def test_admin_list_without_search_returns_newest_users_first(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders
) -> None:
    from app.enums import Role

    admin = await create_user(role=Role.ADMIN)
    newest = await create_user(full_name="Usuária mais recente")

    response = await client.get(
        "/admin/users", params={"page_size": 100}, headers=auth_headers(admin.id)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 2
    assert body["items"][0]["id"] == str(newest.id)
