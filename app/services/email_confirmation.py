import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.email_confirmation_code import EmailConfirmationCode
from app.models.user import User
from app.services.email import EmailService

logger = logging.getLogger(__name__)

CODE_TTL = timedelta(hours=24)
# Matches the app's 30-second "Reenviar e-mail" cooldown, and keeps the public resend
# endpoint from being used to flood someone's inbox.
RESEND_COOLDOWN = timedelta(seconds=30)


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


class EmailConfirmationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.email_service = EmailService()

    async def create_and_send(self, user: User) -> None:
        code = secrets.token_urlsafe(32)
        confirmation = EmailConfirmationCode(
            user_id=user.id,
            code_hash=_hash_code(code),
            expires_at=datetime.now(UTC) + CODE_TTL,
        )
        self.db.add(confirmation)
        await self.db.commit()

        confirm_url = f"{get_settings().api_base_url}/auth/confirm-email/{code}"
        try:
            await self.email_service.send(
                to=user.email,
                subject="Confirme seu cadastro",
                html=(
                    "<p>Bem-vindo(a) à Silpo!</p>"
                    "<p>Clique no botão abaixo para confirmar seu cadastro:</p>"
                    f'<p><a href="{confirm_url}">Confirmar cadastro</a></p>'
                ),
            )
        except Exception:
            # The user and confirmation code are already committed. Failing the
            # registration request here would 500 on the client while leaving
            # behind a user that can never be confirmed (a retry would just hit
            # the "email already registered" conflict). Log and let registration
            # succeed instead; the user can request the email again later.
            logger.exception("Failed to send confirmation email to %s", user.email)

    async def resend(self, email: str) -> None:
        normalized_email = email.strip().lower()
        user = await self.db.scalar(select(User).where(User.email == normalized_email))

        # Silent no-op for unknown, inactive or already confirmed accounts: the endpoint
        # answers the same way either way, so it can't be used to find out who has an account.
        if (
            user is None
            or not user.enabled
            or user.deleted_at is not None
            or user.email_confirmed_at is not None
        ):
            return

        last_sent_at = await self.db.scalar(
            select(func.max(EmailConfirmationCode.created_at)).where(
                EmailConfirmationCode.user_id == user.id
            )
        )
        if last_sent_at is not None and last_sent_at > datetime.now(UTC) - RESEND_COOLDOWN:
            return

        # Earlier links keep working until they expire; whichever one the user clicks confirms.
        await self.create_and_send(user)

    async def confirm(self, code: str) -> User:
        result = await self.db.execute(
            select(EmailConfirmationCode).where(EmailConfirmationCode.code_hash == _hash_code(code))
        )
        confirmation = result.scalar_one_or_none()

        now = datetime.now(UTC)
        invalid_code_exception = HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired confirmation code",
        )
        if (
            confirmation is None
            or confirmation.used_at is not None
            or confirmation.expires_at < now
        ):
            raise invalid_code_exception

        user = await self.db.get(User, confirmation.user_id)
        if user is None:
            raise invalid_code_exception

        confirmation.used_at = now
        user.email_confirmed_at = now
        await self.db.commit()
        await self.db.refresh(user)
        return user
