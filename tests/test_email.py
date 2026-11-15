import smtplib
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.app_setting import AppSetting
from app.services.email import EmailService, SmtpNotConfiguredError


async def test_send_calls_resend_with_expected_payload() -> None:
    service = EmailService()

    with patch("resend.Emails.send", return_value={"id": "email-123"}) as mock_send:
        email_id = await service.send(
            to="user@example.com",
            subject="Welcome",
            html="<p>Hello</p>",
        )

    assert email_id == "email-123"
    mock_send.assert_called_once_with(
        {
            "from": service.from_address,
            "to": ["user@example.com"],
            "subject": "Welcome",
            "html": "<p>Hello</p>",
        }
    )


@pytest.fixture
def smtp_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USERNAME", "silpo@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("EMAIL_FROM", "Silpo <silpo@example.com>")
    get_settings.cache_clear()


@pytest.mark.usefixtures("smtp_settings")
async def test_send_uses_smtp_when_configured(mock_resend_send: MagicMock) -> None:
    service = EmailService()

    with patch("smtplib.SMTP") as mock_smtp_class:
        email_id = await service.send(
            to="user@example.com",
            subject="Welcome",
            html="<p>Hello</p>",
        )

    mock_smtp_class.assert_called_once_with("smtp.example.com", 2525, timeout=10)
    smtp = mock_smtp_class.return_value.__enter__.return_value
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("silpo@example.com", "app-password")
    smtp.send_message.assert_called_once()

    message: EmailMessage = smtp.send_message.call_args[0][0]
    assert message["From"] == "Silpo <silpo@example.com>"
    assert message["To"] == "user@example.com"
    assert message["Subject"] == "Welcome"
    assert message.get_content_type() == "text/html"
    assert message.get_content().strip() == "<p>Hello</p>"
    assert email_id == message["Message-ID"]
    mock_resend_send.assert_not_called()


@pytest.mark.usefixtures("smtp_settings")
async def test_send_propagates_smtp_errors() -> None:
    service = EmailService()

    with patch("smtplib.SMTP") as mock_smtp_class:
        smtp = mock_smtp_class.return_value.__enter__.return_value
        smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Bad credentials")

        with pytest.raises(smtplib.SMTPAuthenticationError):
            await service.send(to="user@example.com", subject="Welcome", html="<p>Hello</p>")

    smtp.send_message.assert_not_called()


@pytest.fixture
def smtp_settings_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    # Como em produção: o ECS injeta os secrets do SMTP, só que vazios.
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USERNAME", "")
    monkeypatch.setenv("SMTP_PASSWORD", "")
    monkeypatch.setenv("EMAIL_FROM", "Silpo <silpo@example.com>")
    get_settings.cache_clear()


async def _store_smtp_credentials(db_session: AsyncSession, username: str, password: str) -> None:
    db_session.add_all(
        [
            AppSetting(key="smtp_username", value=username),
            AppSetting(key="smtp_password", value=password),
        ]
    )
    await db_session.flush()


@pytest.mark.usefixtures("smtp_settings_without_credentials")
async def test_smtp_falls_back_to_credentials_stored_in_the_database(
    db_session: AsyncSession,
) -> None:
    await _store_smtp_credentials(db_session, "db-user@example.com", "db-app-password")
    service = EmailService(db_session)

    with patch("smtplib.SMTP") as mock_smtp_class:
        await service.send(to="user@example.com", subject="Welcome", html="<p>Hello</p>")

    smtp = mock_smtp_class.return_value.__enter__.return_value
    smtp.login.assert_called_once_with("db-user@example.com", "db-app-password")
    smtp.send_message.assert_called_once()
    # O Gmail recusa um From diferente da conta autenticada: mantém o nome, troca o endereço.
    message: EmailMessage = smtp.send_message.call_args[0][0]
    assert message["From"] == "Silpo <db-user@example.com>"


@pytest.mark.usefixtures("smtp_settings_without_credentials")
async def test_smtp_uses_the_sender_stored_in_the_database_when_present(
    db_session: AsyncSession,
) -> None:
    await _store_smtp_credentials(db_session, "db-user@example.com", "db-app-password")
    db_session.add(AppSetting(key="email_from", value="Equipe Silpo <db-user@example.com>"))
    await db_session.flush()
    service = EmailService(db_session)

    with patch("smtplib.SMTP") as mock_smtp_class:
        await service.send(to="user@example.com", subject="Welcome", html="<p>Hello</p>")

    smtp = mock_smtp_class.return_value.__enter__.return_value
    message: EmailMessage = smtp.send_message.call_args[0][0]
    assert message["From"] == "Equipe Silpo <db-user@example.com>"


@pytest.mark.usefixtures("smtp_settings")
async def test_smtp_database_credentials_win_over_the_environment(
    db_session: AsyncSession,
) -> None:
    # Produção: o ECS recebe credenciais erradas que só o admin da AWS consegue trocar.
    await _store_smtp_credentials(db_session, "db-user@example.com", "db-app-password")
    service = EmailService(db_session)

    with patch("smtplib.SMTP") as mock_smtp_class:
        await service.send(to="user@example.com", subject="Welcome", html="<p>Hello</p>")

    smtp = mock_smtp_class.return_value.__enter__.return_value
    smtp.login.assert_called_once_with("db-user@example.com", "db-app-password")
    message: EmailMessage = smtp.send_message.call_args[0][0]
    assert message["From"] == "Silpo <db-user@example.com>"


@pytest.mark.usefixtures("smtp_settings")
@pytest.mark.parametrize("stored_keys", [(), ("smtp_username",), ("smtp_password",)])
async def test_smtp_uses_the_environment_without_a_complete_pair_in_the_database(
    db_session: AsyncSession, stored_keys: tuple[str, ...]
) -> None:
    db_session.add_all([AppSetting(key=key, value="from-db") for key in stored_keys])
    await db_session.flush()
    service = EmailService(db_session)

    with patch("smtplib.SMTP") as mock_smtp_class:
        await service.send(to="user@example.com", subject="Welcome", html="<p>Hello</p>")

    smtp = mock_smtp_class.return_value.__enter__.return_value
    smtp.login.assert_called_once_with("silpo@example.com", "app-password")
    message: EmailMessage = smtp.send_message.call_args[0][0]
    assert message["From"] == "Silpo <silpo@example.com>"


@pytest.mark.usefixtures("smtp_settings_without_credentials")
async def test_smtp_without_credentials_anywhere_fails_before_connecting(
    db_session: AsyncSession,
) -> None:
    service = EmailService(db_session)

    with patch("smtplib.SMTP") as mock_smtp_class:
        with pytest.raises(SmtpNotConfiguredError):
            await service.send(to="user@example.com", subject="Welcome", html="<p>Hello</p>")

    mock_smtp_class.assert_not_called()
