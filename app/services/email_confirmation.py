import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.email_confirmation_code import EmailConfirmationCode
from app.models.user import User
from app.services.email import EmailService

CODE_TTL = timedelta(hours=24)


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
        await self.email_service.send(
            to=user.email,
            subject="Confirme seu cadastro",
            html=(
                "<p>Bem-vindo(a) à Silpo!</p>"
                "<p>Clique no botão abaixo para confirmar seu cadastro:</p>"
                f'<p><a href="{confirm_url}">Confirmar cadastro</a></p>'
            ),
        )

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
