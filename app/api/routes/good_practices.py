from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_current_user, get_good_practice_service
from app.models.user import User
from app.schemas.good_practice import GoodPracticeListResponse
from app.services.good_practice import GoodPracticeService

router = APIRouter(prefix="/good-practices", tags=["good-practices"])


@router.get("", response_model=GoodPracticeListResponse, status_code=status.HTTP_200_OK)
async def list_good_practices(
    daily: bool = Query(False),
    current_user: User = Depends(get_current_user),
    service: GoodPracticeService = Depends(get_good_practice_service),
) -> dict[str, list]:
    if daily:
        practice = await service.get_daily()
        items = [practice] if practice else []
    else:
        items = await service.list_enabled()

    return {"items": items}
