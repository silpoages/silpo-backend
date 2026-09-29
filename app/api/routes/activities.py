import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_activity_service
from app.schemas.activity import ActivityRead
from app.services.activity import ActivityService

router = APIRouter(prefix="/activities", tags=["activities"])


@router.get("/{activity_id}", response_model=ActivityRead)
async def get_activity(
    activity_id: uuid.UUID,
    service: ActivityService = Depends(get_activity_service),
) -> ActivityRead:
    activity = await service.get_configuration(activity_id)
    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )
    return activity