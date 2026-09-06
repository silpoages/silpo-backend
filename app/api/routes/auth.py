from fastapi import APIRouter, Depends, status

from app.api.deps import get_auth_service
from app.models.user import User
from app.schemas.user import UserCreate, UserRead
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create(payload: UserCreate, service: AuthService = Depends(get_auth_service)) -> User:
    return await service.create(payload)
