from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user, get_journey_service
from app.models.user import User
from app.schemas.journey import JourneyRead
from app.services.journey import JourneyService

router = APIRouter(prefix="/journey", tags=["journey"])


@router.get("", response_model=JourneyRead, status_code=status.HTTP_200_OK)
async def get_journey(
    current_user: User = Depends(get_current_user),
    service: JourneyService = Depends(get_journey_service),
) -> JourneyRead:
    return await service.get_current_month(current_user.id)
