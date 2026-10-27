import smtplib
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import get_settings
from app.services.email import EmailService


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
