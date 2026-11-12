import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
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


async def parse_meditation_update_form(
    request: Request,
    name: Annotated[str | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
    max_duration_seconds: Annotated[str | None, Form(description="Duration in seconds")] = None,
    enabled: Annotated[str | None, Form(description="Visibility in the app")] = None,
) -> MeditationUpdate:
    raw_form = await request.form()
    sent: dict[str, str] = {}
    for field, value in (
        ("name", name),
        ("description", description),
        ("max_duration_seconds", max_duration_seconds),
        ("enabled", enabled),
    ):
        if value is not None:
            sent[field] = value
        elif raw_form.get(field) == "":
            sent[field] = ""
    try:
        return MeditationUpdate.model_validate(sent)
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
    audio: Annotated[
        UploadFile | None,
        File(description="Optional new MP3 file, up to 20 MB. Omit to keep the current audio"),
    ] = None,
    form: MeditationUpdate = Depends(parse_meditation_update_form),
    service: MeditationService = Depends(get_meditation_service),
) -> MeditationActivity:
    audio_bytes = await read_validated_mp3(audio) if audio is not None else None
    return await service.update_with_audio(meditation_id, form, audio_bytes)


@router.delete("/{meditation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meditation(
    meditation_id: uuid.UUID,
    service: MeditationService = Depends(get_meditation_service),
) -> None:
    await service.delete(meditation_id)