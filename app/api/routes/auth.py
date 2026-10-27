from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from app.api.deps import (
    get_current_user,
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
    LoginUser,
    RegisterInput,
    RegisterOutput,
    ResendConfirmationInput,
    ResendConfirmationOutput,
    ResetPasswordCodeInput,
    ResetPasswordCodeVerifyInput,
    ResetPasswordInput,
    ResetPasswordOutput,
    ResetPasswordVerifyOutput,
)
from app.services.email_confirmation import EmailConfirmationService
from app.services.password_reset import PasswordResetService
from app.services.user import UserService
from app.templates import render_email_confirmation_page

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


@router.get("/me", response_model=LoginUser, status_code=status.HTTP_200_OK)
async def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    # get_current_user já devolve 401 para token inválido/expirado e conta desativada.
    return current_user


@router.get(
    "/confirm-email/{code}", response_model=ConfirmEmailOutput, status_code=status.HTTP_200_OK
)
async def confirm_email(
    code: str,
    request: Request,
    service: EmailConfirmationService = Depends(get_email_confirmation_service),
) -> dict[str, str] | HTMLResponse:
    # O link do e-mail abre no navegador: quem pede HTML recebe a página no visual do app;
    # clientes da API continuam recebendo JSON.
    wants_html = "text/html" in request.headers.get("accept", "")
    try:
        await service.confirm(code)
    except HTTPException as exc:
        if not wants_html:
            raise
        return HTMLResponse(
            render_email_confirmation_page(confirmed=False), status_code=exc.status_code
        )

    if wants_html:
        return HTMLResponse(render_email_confirmation_page(confirmed=True))
    return {"message": "Email confirmed"}


@router.post(
    "/resend-confirmation",
    response_model=ResendConfirmationOutput,
    status_code=status.HTTP_200_OK,
)
async def resend_confirmation(
    payload: ResendConfirmationInput,
    service: EmailConfirmationService = Depends(get_email_confirmation_service),
) -> dict[str, str]:
    await service.resend(payload.email)
    return {"message": "If this email needs confirmation, a new link has been sent"}


@router.post(
    "/forgot-password", response_model=ForgotPasswordOutput, status_code=status.HTTP_200_OK
)
async def forgot_password(
    payload: ForgotPasswordInput,
    service: PasswordResetService = Depends(get_password_reset_service),
) -> dict[str, str]:
    await service.request_reset(payload.email, payload.method)
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


# Fluxo do app: código de 6 dígitos enviado por e-mail, sempre validado junto com o e-mail.
# Fica fora de /reset-password/{code} para não colidir com o fluxo do link (web).
@router.post(
    "/reset-password-code/verify",
    response_model=ResetPasswordVerifyOutput,
    status_code=status.HTTP_200_OK,
)
async def verify_reset_password_numeric_code(
    payload: ResetPasswordCodeVerifyInput,
    service: PasswordResetService = Depends(get_password_reset_service),
) -> dict[str, str]:
    await service.verify_numeric_code(payload.email, payload.code)
    return {"message": "Valid reset code"}


@router.post(
    "/reset-password-code", response_model=ResetPasswordOutput, status_code=status.HTTP_200_OK
)
async def reset_password_with_numeric_code(
    payload: ResetPasswordCodeInput,
    service: PasswordResetService = Depends(get_password_reset_service),
) -> dict[str, str]:
    await service.reset_password_with_numeric_code(
        payload.email, payload.code, payload.new_password
    )
    return {"message": "Password updated"}
