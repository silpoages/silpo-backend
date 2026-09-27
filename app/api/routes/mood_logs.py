from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_mood_log_service
from app.models.mood_log import MoodLog
from app.models.user import User
from app.schemas.mood_log import MoodLogCreate, MoodLogRead
from app.services.mood_log import MoodLogAlreadyLoggedError, MoodLogService

router = APIRouter(prefix="/mood-logs", tags=["mood-logs"])


@router.post("", response_model=MoodLogRead, status_code=status.HTTP_201_CREATED)
async def create_mood_log(
    payload: MoodLogCreate,
    current_user: User = Depends(get_current_user),
    service: MoodLogService = Depends(get_mood_log_service),
) -> MoodLog:
    try:
        return await service.create(user_id=current_user.id, mood=payload.mood)
    except MoodLogAlreadyLoggedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Você já registrou uma emoção hoje.",
        ) from exc


@router.get("/today", response_model=MoodLogRead | None, status_code=status.HTTP_200_OK)
async def get_today_mood_log(
    current_user: User = Depends(get_current_user),
    service: MoodLogService = Depends(get_mood_log_service),
) -> MoodLog | None:
    return await service.get_today(current_user.id)
