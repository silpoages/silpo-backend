import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid

import resend
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.enums import EmailProvider
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 10

# Chaves em `app_setting` usadas quando SMTP_USERNAME/SMTP_PASSWORD chegam vazios no ambiente
# (produção sem acesso para configurar os secrets do ECS). A variável de ambiente, quando tem
# valor, sempre vence.
SMTP_USERNAME_SETTING = "smtp_username"
SMTP_PASSWORD_SETTING = "smtp_password"


class SmtpNotConfiguredError(RuntimeError):
    pass


class EmailService:
    def __init__(self, db: AsyncSession | None = None) -> None:
        self.settings = get_settings()
        self.db = db
        self.from_address = self.settings.email_from
        resend.api_key = self.settings.resend_api_key

    async def send(self, *, to: str, subject: str, html: str) -> str:
        if self.settings.email_provider == EmailProvider.SMTP:
            username, password = await self._smtp_credentials()
            email_id = await run_in_threadpool(
                self._send_smtp, to, subject, html, username, password
            )
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

    async def _smtp_credentials(self) -> tuple[str, str]:
        username = self.settings.smtp_username
        password = self.settings.smtp_password
        if (not username or not password) and self.db is not None:
            result = await self.db.execute(
                select(AppSetting.key, AppSetting.value).where(
                    AppSetting.key.in_([SMTP_USERNAME_SETTING, SMTP_PASSWORD_SETTING])
                )
            )
            stored = {key: value for key, value in result.tuples().all()}
            username = username or stored.get(SMTP_USERNAME_SETTING, "")
            password = password or stored.get(SMTP_PASSWORD_SETTING, "")

        if not username or not password:
            raise SmtpNotConfiguredError(
                "SMTP credentials missing: set SMTP_USERNAME/SMTP_PASSWORD or the "
                f"'{SMTP_USERNAME_SETTING}'/'{SMTP_PASSWORD_SETTING}' rows in app_setting"
            )
        return username, password

    def _send_smtp(self, to: str, subject: str, html: str, username: str, password: str) -> str:
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
            smtp.login(username, password)
            smtp.send_message(message)
        return str(message["Message-ID"])
