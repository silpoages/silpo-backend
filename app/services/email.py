import logging

import resend
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self) -> None:
        settings = get_settings()
        self.from_address = settings.email_from
        resend.api_key = settings.resend_api_key

    async def send(self, *, to: str, subject: str, html: str) -> str:
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
