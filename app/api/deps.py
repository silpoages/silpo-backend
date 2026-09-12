import uuid 
from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.db.session import get_db
from app.service.user import Users 

DbSession = AsyncGenerator[AsyncSession, None]

get_session = get_db

def get_user_service(db: AsyncSession = Depends(get_session)) -> Users:
    return Users(db)

async def get_current_user (user_id: uuid.UUID = Depends(get_current_user_id), db: AsyncSession = Depends(get_session)):
    user = await db.get(Users, user_id) 
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if not user.enabled or user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User inactive",
        )
    return user