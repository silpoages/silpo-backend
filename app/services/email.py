import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid

import resend
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.enums import EmailProvider

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 10


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.from_address = self.settings.email_from
        resend.api_key = self.settings.resend_api_key

    async def send(self, *, to: str, subject: str, html: str) -> str:
        if self.settings.email_provider == EmailProvider.SMTP:
            email_id = await run_in_threadpool(self._send_smtp, to, subject, html)
        else:
            email_id = await run_in_threadpool(self._send_resend, to, subject, html)
        logger.info("Email sent to %s (id=%s)", to, email_id)
        return email_id

    def _send_resend(self, to: str, subject: str, html: str) -> str:
        response = resend.Emails.send(
            {
                "from": self.from_address,
                "to": [to],
                "subject": subject,
                "html": html,
            }
        )
        email_id: str = response["id"]
        return email_id

    def _send_smtp(self, to: str, subject: str, html: str) -> str:
        message = EmailMessage()
        message["From"] = self.from_address
        message["To"] = to
        message["Subject"] = subject
        message["Message-ID"] = make_msgid()
        message.set_content(html, subtype="html")

        with smtplib.SMTP(
            self.settings.smtp_host, self.settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS
        ) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(self.settings.smtp_username, self.settings.smtp_password)
            smtp.send_message(message)
        return str(message["Message-ID"])
