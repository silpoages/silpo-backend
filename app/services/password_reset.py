import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.enums import PasswordResetMethod
from app.models.password_reset_code import PasswordResetCode
from app.models.user import User
from app.services.email import EmailService

logger = logging.getLogger(__name__)

# Shorter than the email-confirmation code's TTL: this code grants control over the
# account's password, so it should only be usable for a short window after the request.
CODE_TTL = timedelta(hours=1)
# The 6-digit code typed in the mobile app is guessable, so it lives much less and only
# survives a few wrong attempts (1 in 200,000 odds of guessing it before it's burned).
NUMERIC_CODE_TTL = timedelta(minutes=15)
NUMERIC_CODE_LENGTH = 6
NUMERIC_CODE_MAX_FAILED_ATTEMPTS = 5

_INVALID_CODE_EXCEPTION = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="Invalid or expired reset code",
)


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _hash_numeric_code(reset_code_id: uuid.UUID, code: str) -> str:
    # Salted with the row id: different users can get the same 6 digits, and code_hash is unique.
    return _hash_code(f"{reset_code_id}:{code}")


class PasswordResetService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.email_service = EmailService()

    async def request_reset(
        self, email: str, method: PasswordResetMethod = PasswordResetMethod.LINK
    ) -> None:
        user = await self._get_active_user(email)

        # Always respond the same way whether or not the email is registered, so this
        # endpoint can't be used to find out which emails have an account.
        if user is None:
            return

        if method == PasswordResetMethod.CODE:
            subject, html = await self._create_numeric_code(user)
        else:
            subject, html = await self._create_link_code(user)

        try:
            await self.email_service.send(to=user.email, subject=subject, html=html)
        except Exception:
            # The code is already committed; a failed send just means the user won't
            # get the email this time around (same as request_reset's silent no-op for
            # an unknown email) rather than a 500 that would hint the address exists.
            logger.exception("Failed to send password reset email to %s", user.email)

    async def _get_active_user(self, email: str) -> User | None:
        normalized_email = email.strip().lower()
        result = await self.db.execute(select(User).where(User.email == normalized_email))
        user = result.scalar_one_or_none()
        if user is None or not user.enabled or user.deleted_at is not None:
            return None
        return user

    async def _create_link_code(self, user: User) -> tuple[str, str]:
        code = secrets.token_urlsafe(32)
        reset_code = PasswordResetCode(
            user_id=user.id,
            code_hash=_hash_code(code),
            method=PasswordResetMethod.LINK,
            expires_at=datetime.now(UTC) + CODE_TTL,
        )
        self.db.add(reset_code)
        await self.db.commit()

        reset_url = f"{get_settings().web_app_url}/reset-password?code={code}"
        return (
            "Redefinição de senha",
            "<p>Recebemos um pedido para redefinir a senha da sua conta.</p>"
            "<p>Clique no botão abaixo para escolher uma nova senha:</p>"
            f'<p><a href="{reset_url}">Redefinir senha</a></p>'
            "<p>Se você não pediu isso, pode ignorar este e-mail.</p>",
        )

    async def _create_numeric_code(self, user: User) -> tuple[str, str]:
        now = datetime.now(UTC)
        # Only the latest code works: asking again (e.g. "reenviar código") burns the previous
        # ones, so piling up requests doesn't pile up guesses.
        await self.db.execute(
            update(PasswordResetCode)
            .where(
                PasswordResetCode.user_id == user.id,
                PasswordResetCode.method == PasswordResetMethod.CODE,
                PasswordResetCode.used_at.is_(None),
            )
            .values(used_at=now)
        )

        code = f"{secrets.randbelow(10**NUMERIC_CODE_LENGTH):0{NUMERIC_CODE_LENGTH}d}"
        reset_code_id = uuid.uuid4()
        self.db.add(
            PasswordResetCode(
                id=reset_code_id,
                user_id=user.id,
                code_hash=_hash_numeric_code(reset_code_id, code),
                method=PasswordResetMethod.CODE,
                expires_at=now + NUMERIC_CODE_TTL,
            )
        )
        await self.db.commit()

        minutes = int(NUMERIC_CODE_TTL.total_seconds() // 60)
        return (
            "Seu código para redefinir a senha",
            "<p>Recebemos um pedido para redefinir a senha da sua conta.</p>"
            "<p>Digite este código no app Silpo:</p>"
            f'<p style="font-size:28px;font-weight:bold;letter-spacing:6px">{code}</p>'
            f"<p>Ele vale por {minutes} minutos.</p>"
            "<p>Se você não pediu isso, pode ignorar este e-mail.</p>",
        )

    async def _get_valid_code(self, code: str) -> PasswordResetCode:
        result = await self.db.execute(
            select(PasswordResetCode).where(
                PasswordResetCode.code_hash == _hash_code(code),
                # Numeric codes must go through the email-scoped, attempt-limited path.
                PasswordResetCode.method == PasswordResetMethod.LINK,
            )
        )
        reset_code = result.scalar_one_or_none()

        now = datetime.now(UTC)
        if reset_code is None or reset_code.used_at is not None or reset_code.expires_at < now:
            raise _INVALID_CODE_EXCEPTION
        return reset_code

    async def _get_valid_numeric_code(self, email: str, code: str) -> PasswordResetCode:
        user = await self._get_active_user(email)
        if user is None:
            raise _INVALID_CODE_EXCEPTION

        result = await self.db.execute(
            select(PasswordResetCode)
            .where(
                PasswordResetCode.user_id == user.id,
                PasswordResetCode.method == PasswordResetMethod.CODE,
                PasswordResetCode.used_at.is_(None),
            )
            .order_by(PasswordResetCode.created_at.desc())
            .limit(1)
        )
        reset_code = result.scalar_one_or_none()

        if (
            reset_code is None
            or reset_code.expires_at < datetime.now(UTC)
            or reset_code.failed_attempts >= NUMERIC_CODE_MAX_FAILED_ATTEMPTS
        ):
            raise _INVALID_CODE_EXCEPTION

        if not hmac.compare_digest(reset_code.code_hash, _hash_numeric_code(reset_code.id, code)):
            await self.db.execute(
                update(PasswordResetCode)
                .where(PasswordResetCode.id == reset_code.id)
                .values(failed_attempts=PasswordResetCode.failed_attempts + 1)
            )
            await self.db.commit()
            raise _INVALID_CODE_EXCEPTION
        return reset_code

    async def verify(self, code: str) -> None:
        # Read-only on purpose: a frontend loading the "choose a new password" screen
        # calls this to decide whether to show the form or an error, and e-mail link
        # scanners that GET every link in an incoming email shouldn't be able to burn
        # the code before the real user clicks it.
        await self._get_valid_code(code)

    async def verify_numeric_code(self, email: str, code: str) -> None:
        # Lets the app check the code before asking for the new password; a wrong guess
        # still counts against the attempt limit.
        await self._get_valid_numeric_code(email, code)

    async def reset_password(self, code: str, new_password: str) -> User:
        reset_code = await self._get_valid_code(code)
        return await self._apply_new_password(reset_code, new_password)

    async def reset_password_with_numeric_code(
        self, email: str, code: str, new_password: str
    ) -> User:
        reset_code = await self._get_valid_numeric_code(email, code)
        return await self._apply_new_password(reset_code, new_password)

    async def _apply_new_password(self, reset_code: PasswordResetCode, new_password: str) -> User:
        user = await self.db.get(User, reset_code.user_id)
        if user is None:
            raise _INVALID_CODE_EXCEPTION

        user.password = hash_password(new_password)
        reset_code.used_at = datetime.now(UTC)
        # Usar o link enviado por e-mail prova que a pessoa controla o endereço. Isso
        # libera o login de contas criadas pelo admin, que nunca receberam a confirmação.
        if user.email_confirmed_at is None:
            user.email_confirmed_at = reset_code.used_at
        await self.db.commit()
        await self.db.refresh(user)
        return user
