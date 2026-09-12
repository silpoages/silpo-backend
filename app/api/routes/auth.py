from typing import Any

from fastapi import APIRouter, Depends, status

from app.api.deps import get_user_service
from app.schemas.auth import LoginInput, LoginOutput
from app.services.users import UsersService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginOutput, status_code=status.HTTP_200_OK)
async def login(
    payload: LoginInput,
    service: UsersService = Depends(get_user_service),
) -> dict[str, Any]:
    return await service.login(payload.email, payload.password)
