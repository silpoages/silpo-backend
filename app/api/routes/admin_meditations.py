import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.api.deps import get_current_admin, get_meditation_service
from app.models.meditation_activity import MeditationActivity
from app.models.user import User
from app.schemas.meditation import MeditationBase, MeditationRead, MeditationUpdate
from app.services.meditation import MeditationService
from app.services.mp3_validation import read_validated_mp3

router = APIRouter(
    prefix="/admin/meditations",
    tags=["admin-meditations"],
    dependencies=[Depends(get_current_admin)],
)


def parse_meditation_form(
    name: Annotated[str, Form()],
    description: Annotated[str, Form()],
    max_duration_seconds: Annotated[str, Form(description="Duration in seconds")],
    enabled: Annotated[str, Form(description="Visibility in the app")] = "true",
) -> MeditationBase:
    try:
        return MeditationBase(
            name=name,
            description=description,
            max_duration_seconds=max_duration_seconds,
            enabled=enabled,
        )
    except ValidationError as exc:
        errors = exc.errors(include_url=False, include_context=False)
        for error in errors:
            error["loc"] = ("body", *error["loc"])
        raise RequestValidationError(errors) from exc


@router.post("", response_model=MeditationRead, status_code=status.HTTP_201_CREATED)
async def create_meditation(
    audio: Annotated[UploadFile, File(description="MP3 file, up to 20 MB")],
    form: MeditationBase = Depends(parse_meditation_form),
    current_admin: User = Depends(get_current_admin),
    service: MeditationService = Depends(get_meditation_service),
) -> MeditationActivity:
    audio_bytes = await read_validated_mp3(audio)
    return await service.create_with_audio(form, audio_bytes)


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