from unittest.mock import patch

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
