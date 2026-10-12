from fastapi import APIRouter, Depends, status

from app.api.deps import get_good_practice_service, require_admin
from app.models.good_practice import GoodPractice
from app.models.user import User
from app.schemas.good_practice import GoodPracticeAdminRead, GoodPracticeCreate
from app.services.good_practice import GoodPracticeService

router = APIRouter(prefix="/admin/good-practices", tags=["admin-good-practices"])


@router.post("", response_model=GoodPracticeAdminRead, status_code=status.HTTP_201_CREATED)
async def create_good_practice(
    payload: GoodPracticeCreate,
    current_admin: User = Depends(require_admin),
    service: GoodPracticeService = Depends(get_good_practice_service),
) -> GoodPractice:
    return await service.create(payload)
