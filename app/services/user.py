import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def delete(self, user_id: uuid.UUID) -> bool:
        user = await self.db.get(User, user_id)

        if user is None:
            return False

        user.enabled = False
        user.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()

        return True