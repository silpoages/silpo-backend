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


async def test_send_uses_local_smtp_when_app_env_is_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    get_settings.cache_clear()
    try:
        service = EmailService()

        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp: MagicMock = mock_smtp_cls.return_value.__enter__.return_value
            email_id = await service.send(
                to="user@example.com",
                subject="Welcome",
                html="<p>Hello</p>",
            )
    finally:
        get_settings.cache_clear()

    assert email_id
    mock_smtp_cls.assert_called_once_with(service.smtp_host, service.smtp_port)
    sent_message = mock_smtp.send_message.call_args[0][0]
    assert sent_message["To"] == "user@example.com"
    assert sent_message["Subject"] == "Welcome"
