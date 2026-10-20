import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_admin, get_good_practice_service
from app.models.user import User
from app.services.good_practice import GoodPracticeService

router = APIRouter(prefix="/admin/good-practices", tags=["admin-good-practices"])


@router.delete("/{good_practice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_good_practice(
    good_practice_id: uuid.UUID,
    current_admin: User = Depends(get_current_admin),
    service: GoodPracticeService = Depends(get_good_practice_service),
) -> None:
    await service.delete(good_practice_id)
