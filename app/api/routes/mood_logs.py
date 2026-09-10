from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user, get_mood_log_service
from app.models.user import User
from app.schemas.mood_log import MoodLogListResponse
from app.services.mood_log import MoodLogService

router = APIRouter(prefix="/mood-logs", tags=["mood-logs"])


@router.get("", response_model=MoodLogListResponse)
async def list_mood_logs(
    date: date | None = Query(
        None,
        description="Filtrar por data especifica",
    ),
    current_user: User = Depends(get_current_user),
    service: MoodLogService = Depends(get_mood_log_service),
) -> MoodLogListResponse:
    logs = await service.list_by_user(user_id=current_user.id, log_date=date)
    return MoodLogListResponse(items=logs)
