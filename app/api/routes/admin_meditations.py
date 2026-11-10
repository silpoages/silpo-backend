import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_admin, get_meditation_service
from app.models.meditation_activity import MeditationActivity
from app.schemas.meditation import MeditationRead, MeditationUpdate
from app.services.meditation import MeditationService

router = APIRouter(
    prefix="/admin/meditations",
    tags=["admin-meditations"],
    dependencies=[Depends(get_current_admin)],
)


@router.patch("/{meditation_id}", response_model=MeditationRead, status_code=status.HTTP_200_OK)
async def update_meditation(
    meditation_id: uuid.UUID,
    payload: MeditationUpdate,
    service: MeditationService = Depends(get_meditation_service),
) -> MeditationActivity:
    
    if "audio_url" in payload.model_fields_set:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="audio_url cannot be set directly",
        )
    return await service.update(meditation_id, payload)


@router.delete("/{meditation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meditation(
    meditation_id: uuid.UUID,
    service: MeditationService = Depends(get_meditation_service),
) -> None:
    await service.delete(meditation_id)