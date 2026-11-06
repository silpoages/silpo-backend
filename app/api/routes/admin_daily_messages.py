import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_current_admin, get_daily_message_service
from app.models.daily_message import DailyMessage
from app.schemas.daily_message import (
    DailyMessageCreate,
    DailyMessageListResponse,
    DailyMessageRead,
    DailyMessageUpdate,
)
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


@router.post("", response_model=DailyMessageRead, status_code=status.HTTP_201_CREATED)
async def create_daily_message(
    payload: DailyMessageCreate,
    service: DailyMessageService = Depends(get_daily_message_service),
) -> DailyMessage:
    return await service.create(payload)


@router.patch("/{message_id}", response_model=DailyMessageRead, status_code=status.HTTP_200_OK)
async def update_daily_message(
    message_id: uuid.UUID,
    payload: DailyMessageUpdate,
    service: DailyMessageService = Depends(get_daily_message_service),
) -> DailyMessage:
    return await service.update(message_id, payload)
