from typing import Any

from fastapi import APIRouter, Depends, status

from app.api.deps import get_user_service
from app.models.user import User
from app.schemas.auth import LoginInput, LoginOutput, RegisterInput, RegisterOutput
from app.services.users import UsersService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterOutput, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterInput,
    service: UsersService = Depends(get_user_service),
) -> User:
    return await service.register(payload.email, payload.password)


@router.post("/login", response_model=LoginOutput, status_code=status.HTTP_200_OK)
async def login(
    payload: LoginInput,
    service: UsersService = Depends(get_user_service),
) -> dict[str, Any]:
    return await service.login(payload.email, payload.password)
