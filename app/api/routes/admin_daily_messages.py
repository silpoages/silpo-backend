from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_current_admin, get_daily_message_service
from app.schemas.daily_message import DailyMessageListResponse
from app.services.daily_message import DailyMessageService

router = APIRouter(
    prefix="/admin/daily-messages",
    tags=["admin-daily-messages"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("", response_model=DailyMessageListResponse, status_code=status.HTTP_200_OK)
async def list_daily_messages(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=140)] = None,
    enabled: bool | None = None,
    service: DailyMessageService = Depends(get_daily_message_service),
) -> dict[str, Any]:
    items = await service.list_paginated(page, page_size, search, enabled)
    counts = await service.count_by_status(search)
    return {"items": items, "page": page, "page_size": page_size, **counts}
