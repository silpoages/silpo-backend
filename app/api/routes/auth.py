from typing import Any

from fastapi import APIRouter, Depends, status

from app.api.deps import (
    get_email_confirmation_service,
    get_password_reset_service,
    get_user_service,
)
from app.models.user import User
from app.schemas.auth import (
    ConfirmEmailOutput,
    ForgotPasswordInput,
    ForgotPasswordOutput,
    LoginInput,
    LoginOutput,
    RegisterInput,
    RegisterOutput,
    ResetPasswordInput,
    ResetPasswordOutput,
    ResetPasswordVerifyOutput,
)
from app.services.email_confirmation import EmailConfirmationService
from app.services.password_reset import PasswordResetService
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


@router.post(
    "/forgot-password", response_model=ForgotPasswordOutput, status_code=status.HTTP_200_OK
)
async def forgot_password(
    payload: ForgotPasswordInput,
    service: PasswordResetService = Depends(get_password_reset_service),
) -> dict[str, str]:
    await service.request_reset(payload.email)
    return {"message": "If this email is registered, a reset link has been sent"}


@router.get(
    "/reset-password/{code}",
    response_model=ResetPasswordVerifyOutput,
    status_code=status.HTTP_200_OK,
)
async def verify_reset_password_code(
    code: str,
    service: PasswordResetService = Depends(get_password_reset_service),
) -> dict[str, str]:
    await service.verify(code)
    return {"message": "Valid reset code"}


@router.post(
    "/reset-password/{code}", response_model=ResetPasswordOutput, status_code=status.HTTP_200_OK
)
async def reset_password(
    code: str,
    payload: ResetPasswordInput,
    service: PasswordResetService = Depends(get_password_reset_service),
) -> dict[str, str]:
    await service.reset_password(code, payload.new_password)
    return {"message": "Password updated"}
