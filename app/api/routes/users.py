from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user, get_user_service
from app.models.user import User
from app.schemas.users import UserCreate, UserRead
from app.services.users import UsersService

router = APIRouter(prefix="/users", tags=["users"])


@router.patch("", response_model=UserRead, status_code=status.HTTP_200_OK)
async def update_user(
    payload: UserCreate,
    current_user: User = Depends(get_current_user),
    service: UsersService = Depends(get_user_service),
) -> User:
    return await service.update_user(user_id=current_user.id, payload=payload.model_dump())
