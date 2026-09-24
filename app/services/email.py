import logging
import smtplib
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import resend
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self) -> None:
        settings = get_settings()
        self.from_address = settings.email_from
        self.use_smtp = settings.app_env == "local"
        self.smtp_host = settings.smtp_host
        self.smtp_port = settings.smtp_port
        resend.api_key = settings.resend_api_key

    async def send(self, *, to: str, subject: str, html: str) -> str:
        if self.use_smtp:
            return await run_in_threadpool(self._send_via_smtp, to, subject, html)
        return await self._send_via_resend(to, subject, html)

    async def _send_via_resend(self, to: str, subject: str, html: str) -> str:
        response = await run_in_threadpool(
            resend.Emails.send,
            {
                "from": self.from_address,
                "to": [to],
                "subject": subject,
                "html": html,
            },
        )
        email_id: str = response["id"]
        logger.info("Email sent to %s (id=%s)", to, email_id)
        return email_id

    def _send_via_smtp(self, to: str, subject: str, html: str) -> str:
        message = MIMEMultipart("alternative")
        message["From"] = self.from_address
        message["To"] = to
        message["Subject"] = subject
        message.attach(MIMEText(html, "html"))

        with smtplib.SMTP(self.smtp_host, self.smtp_port) as smtp:
            smtp.send_message(message)

        email_id = str(uuid.uuid4())
        logger.info(
            "Email sent to %s via local SMTP %s:%s (id=%s)",
            to,
            self.smtp_host,
            self.smtp_port,
            email_id,
        )
        return email_id
