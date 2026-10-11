import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user, get_good_practice_service
from app.models.good_practice import GoodPractice
from app.models.user import User
from app.schemas.good_practice import GoodPracticeAdminRead, GoodPracticeUpdate
from app.services.good_practice import GoodPracticeService

router = APIRouter(prefix="/admin/good-practices", tags=["admin-good-practices"])


@router.patch(
    "/{good_practice_id}",
    response_model=GoodPracticeAdminRead,
    status_code=status.HTTP_200_OK,
)
async def update_good_practice(
    good_practice_id: uuid.UUID,
    payload: GoodPracticeUpdate,
    current_user: User = Depends(get_current_user),
    service: GoodPracticeService = Depends(get_good_practice_service),
) -> GoodPractice:
    return await service.update(
        current_user,
        good_practice_id,
        payload.model_dump(exclude_unset=True),
    )
