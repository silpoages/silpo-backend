import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_current_admin, get_good_practice_service
from app.models.good_practice import GoodPractice
from app.models.user import User
from app.schemas.good_practice import (
    GoodPracticeAdminListResponse,
    GoodPracticeAdminRead,
    GoodPracticeUpdate,
)
from app.services.good_practice import GoodPracticeService

router = APIRouter(prefix="/admin/good-practices", tags=["admin-good-practices"])


@router.get("", response_model=GoodPracticeAdminListResponse, status_code=status.HTTP_200_OK)
async def list_admin_good_practices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    enabled: bool | None = Query(None),
    current_admin: User = Depends(get_current_admin),
    service: GoodPracticeService = Depends(get_good_practice_service),
) -> dict[str, Any]:
    items, total = await service.list_for_admin(
        page=page, page_size=page_size, search=search, enabled=enabled
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.patch(
    "/{good_practice_id}",
    response_model=GoodPracticeAdminRead,
    status_code=status.HTTP_200_OK,
)
async def update_good_practice(
    good_practice_id: uuid.UUID,
    payload: GoodPracticeUpdate,
    current_admin: User = Depends(get_current_admin),
    service: GoodPracticeService = Depends(get_good_practice_service),
) -> GoodPractice:
    return await service.update(good_practice_id, payload.model_dump(exclude_unset=True))
