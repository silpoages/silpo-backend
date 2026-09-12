import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_token(self, token: str) -> User | None:
        """
        Validate token and return user.
        For now, token is simply the user_id as a string (Bearer <user_id>).
        In production, use proper JWT validation.
        """
        try:
            user_id = uuid.UUID(token)
            result = await self.db.execute(select(User).where(User.id == user_id))
            return result.scalar_one_or_none()
        except (ValueError, TypeError):
            return None
