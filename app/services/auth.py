from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.enums import Role
from app.models.user import User
from app.schemas.user import UserCreate


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, payload: UserCreate) -> User:
        user = User(
            email=payload.email,
            password=hash_password(payload.password),
            role=Role.USER,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user
