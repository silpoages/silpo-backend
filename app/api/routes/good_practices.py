import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_current_user, get_good_practice_service
from app.models.good_practice_log import GoodPracticeLog
from app.models.user import User
from app.schemas.good_practice import (
    GoodPracticeCompletionRead,
    GoodPracticeListResponse,
    GoodPracticeRead,
)
from app.services.good_practice import GoodPracticeService

router = APIRouter(prefix="/good-practices", tags=["good-practices"])


@router.get(
    "",
    response_model=GoodPracticeListResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
async def list_good_practices(
    daily: bool = Query(False),
    current_user: User = Depends(get_current_user),
    service: GoodPracticeService = Depends(get_good_practice_service),
) -> GoodPracticeListResponse:
    if daily:
        practice = await service.get_daily()
        if practice is None:
            return GoodPracticeListResponse(items=[])

        item = GoodPracticeRead.model_validate(practice)
        item.completed_today = await service.is_completed_today(current_user.id, practice.id)
        return GoodPracticeListResponse(items=[item])

    practices = await service.list_enabled()
    return GoodPracticeListResponse(
        items=[GoodPracticeRead.model_validate(practice) for practice in practices]
    )


@router.post(
    "/{good_practice_id}/complete",
    response_model=GoodPracticeCompletionRead,
    status_code=status.HTTP_201_CREATED,
)
async def complete_good_practice(
    good_practice_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: GoodPracticeService = Depends(get_good_practice_service),
) -> GoodPracticeLog:
    return await service.complete(user_id=current_user.id, good_practice_id=good_practice_id)
