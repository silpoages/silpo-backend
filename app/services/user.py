import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User

class UserService:
    
    @staticmethod
    async def delete_user(session: AsyncSession, user_id: uuid.UUID) -> bool:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()

        if not user:
            return False

        user.enabled = False
        user.deleted_at = datetime.now(timezone.utc)
        await session.commit()
        
        return True