import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_user_service, require_admin
from app.enums import Role
from app.models.user import User
from app.schemas.user import AdminUserListResponse, AdminUserRead
from app.services.user import UserService

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("", response_model=AdminUserListResponse, status_code=status.HTTP_200_OK)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    role: Role | None = Query(None),
    enabled: bool | None = Query(None),
    current_admin: User = Depends(require_admin),
    service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    items, total = await service.list_users(
        page=page, page_size=page_size, search=search, role=role, enabled=enabled
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{user_id}", response_model=AdminUserRead, status_code=status.HTTP_200_OK)
async def get_user(
    user_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
    service: UserService = Depends(get_user_service),
) -> User:
    return await service.get_user_by_id(user_id)
