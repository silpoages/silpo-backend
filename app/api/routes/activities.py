from fastapi import APIRouter, Depends, status

from app.api.deps import get_activity_service, get_current_user
from app.models.activity import Activity
from app.models.user import User
from app.schemas.activity import ActivityListResponse
from app.services.activity import ActivityService

router = APIRouter(prefix="/activities", tags=["activities"])


@router.get("", response_model=ActivityListResponse, status_code=status.HTTP_200_OK)
async def list_activities(
    current_user: User = Depends(get_current_user),
    service: ActivityService = Depends(get_activity_service),
) -> dict[str, list[Activity]]:
    items = await service.list_available()
    return {"items": items}
