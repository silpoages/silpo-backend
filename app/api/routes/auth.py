from typing import Any

from fastapi import APIRouter, Depends, status

from app.api.deps import get_email_confirmation_service, get_user_service
from app.models.user import User
from app.schemas.auth import (
    ConfirmEmailOutput,
    LoginInput,
    LoginOutput,
    RegisterInput,
    RegisterOutput,
)
from app.services.email_confirmation import EmailConfirmationService
from app.services.user import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterOutput, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterInput,
    service: UserService = Depends(get_user_service),
) -> User:
    return await service.register(payload.email, payload.password)


@router.post("/login", response_model=LoginOutput, status_code=status.HTTP_200_OK)
async def login(
    payload: LoginInput,
    service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    return await service.login(payload.email, payload.password)


@router.get(
    "/confirm-email/{code}", response_model=ConfirmEmailOutput, status_code=status.HTTP_200_OK
)
async def confirm_email(
    code: str,
    service: EmailConfirmationService = Depends(get_email_confirmation_service),
) -> dict[str, str]:
    await service.confirm(code)
    return {"message": "Email confirmed"}
