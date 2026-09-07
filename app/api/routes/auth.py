from fastapi import APIRouter, Depends, status

from app.api.deps import get_user_service
from app.schemas.auth import LoginInput
from app.services.user import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", status_code=status.HTTP_200_OK)
async def login(
    payload: LoginInput,
    service: UserService = Depends(get_user_service),
):
    return await service.login(payload.email, payload.password)