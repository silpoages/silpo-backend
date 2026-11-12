from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user, get_daily_message_service
from app.models.daily_message import DailyMessage
from app.models.user import User
from app.schemas.daily_message import DailyMessageToday
from app.services.daily_message import DailyMessageService

router = APIRouter(prefix="/daily-messages", tags=["daily-messages"])


@router.get("/today", response_model=DailyMessageToday | None, status_code=status.HTTP_200_OK)
async def get_today_daily_message(
    current_user: User = Depends(get_current_user),
    service: DailyMessageService = Depends(get_daily_message_service),
) -> DailyMessage | None:
    return await service.get_today()
