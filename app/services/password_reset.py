import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.password_reset_code import PasswordResetCode
from app.models.user import User
from app.services.email import EmailService

logger = logging.getLogger(__name__)

# Shorter than the email-confirmation code's TTL: this code grants control over the
# account's password, so it should only be usable for a short window after the request.
CODE_TTL = timedelta(hours=1)

_INVALID_CODE_EXCEPTION = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="Invalid or expired reset code",
)


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


class PasswordResetService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.email_service = EmailService()

    async def request_reset(self, email: str) -> None:
        normalized_email = email.strip().lower()
        result = await self.db.execute(select(User).where(User.email == normalized_email))
        user = result.scalar_one_or_none()

        # Always respond the same way whether or not the email is registered, so this
        # endpoint can't be used to find out which emails have an account.
        if user is None or not user.enabled or user.deleted_at is not None:
            return

        code = secrets.token_urlsafe(32)
        reset_code = PasswordResetCode(
            user_id=user.id,
            code_hash=_hash_code(code),
            expires_at=datetime.now(UTC) + CODE_TTL,
        )
        self.db.add(reset_code)
        await self.db.commit()

        reset_url = f"{get_settings().web_app_url}/reset-password?code={code}"
        try:
            await self.email_service.send(
                to=user.email,
                subject="Redefinição de senha",
                html=(
                    "<p>Recebemos um pedido para redefinir a senha da sua conta.</p>"
                    "<p>Clique no botão abaixo para escolher uma nova senha:</p>"
                    f'<p><a href="{reset_url}">Redefinir senha</a></p>'
                    "<p>Se você não pediu isso, pode ignorar este e-mail.</p>"
                ),
            )
        except Exception:
            # The code is already committed; a failed send just means the user won't
            # get the email this time around (same as request_reset's silent no-op for
            # an unknown email) rather than a 500 that would hint the address exists.
            logger.exception("Failed to send password reset email to %s", user.email)

    async def _get_valid_code(self, code: str) -> PasswordResetCode:
        result = await self.db.execute(
            select(PasswordResetCode).where(PasswordResetCode.code_hash == _hash_code(code))
        )
        reset_code = result.scalar_one_or_none()

        now = datetime.now(UTC)
        if reset_code is None or reset_code.used_at is not None or reset_code.expires_at < now:
            raise _INVALID_CODE_EXCEPTION
        return reset_code

    async def verify(self, code: str) -> None:
        # Read-only on purpose: a frontend loading the "choose a new password" screen
        # calls this to decide whether to show the form or an error, and e-mail link
        # scanners that GET every link in an incoming email shouldn't be able to burn
        # the code before the real user clicks it.
        await self._get_valid_code(code)

    async def reset_password(self, code: str, new_password: str) -> User:
        reset_code = await self._get_valid_code(code)

        user = await self.db.get(User, reset_code.user_id)
        if user is None:
            raise _INVALID_CODE_EXCEPTION

        user.password = hash_password(new_password)
        reset_code.used_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(user)
        return user
