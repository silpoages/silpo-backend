import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_current_admin, get_user_service
from app.enums import Gender, Role
from app.models.user import User
from app.schemas.user import (
    AdminUserCreate,
    AdminUserListResponse,
    AdminUserRead,
    AdminUserUpdate,
)
from app.services.user import UserService

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.post("", response_model=AdminUserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: AdminUserCreate,
    current_admin: User = Depends(get_current_admin),
    service: UserService = Depends(get_user_service),
) -> User:
    return await service.create_by_admin(payload.model_dump())


@router.get("", response_model=AdminUserListResponse, status_code=status.HTTP_200_OK)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    role: Role | None = Query(None),
    enabled: bool | None = Query(None),
    gender: Gender | None = Query(None),
    current_admin: User = Depends(get_current_admin),
    service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    items, total = await service.list_users(
        page=page,
        page_size=page_size,
        search=search,
        role=role,
        enabled=enabled,
        gender=gender,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{user_id}", response_model=AdminUserRead, status_code=status.HTTP_200_OK)
async def get_user(
    user_id: uuid.UUID,
    current_admin: User = Depends(get_current_admin),
    service: UserService = Depends(get_user_service),
) -> User:
    return await service.get_user_by_id(user_id)


@router.patch("/{user_id}", response_model=AdminUserRead, status_code=status.HTTP_200_OK)
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    current_admin: User = Depends(get_current_admin),
    service: UserService = Depends(get_user_service),
) -> User:
    return await service.update_by_admin(
        user_id, payload.model_dump(exclude_unset=True), current_admin
    )
