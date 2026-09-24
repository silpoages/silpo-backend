from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user, get_mood_log_service
from app.models.mood_log import MoodLog
from app.models.user import User
from app.schemas.mood_log import MoodLogCreate, MoodLogGet, MoodLogGetResponse, MoodLogRead
from app.services.mood_log import MoodLogService

router = APIRouter(prefix="/mood-logs", tags=["mood-logs"])


@router.post("", response_model=MoodLogRead, status_code=status.HTTP_201_CREATED)
async def create_mood_log(
    payload: MoodLogCreate,
    current_user: User = Depends(get_current_user),
    service: MoodLogService = Depends(get_mood_log_service),
) -> MoodLog:
    return await service.create(user_id=current_user.id, mood=payload.mood)


@router.get("", response_model=list[MoodLogGetResponse])
async def get_mood_log(
    payload: MoodLogGet,
    current_user: User = Depends(get_current_user),
    service: MoodLogService = Depends(get_mood_log_service),
) -> list[MoodLog]:
    return await service.list_by_date(user_id=current_user.id, log_date=payload.date)
