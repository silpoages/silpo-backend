import re

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse, Response

from app.services.audio_storage import (
    AUDIO_CONTENT_TYPE,
    AudioStorage,
    LocalAudioStorage,
    S3AudioStorage,
    get_audio_storage,
)
from app.services.meditation import MEDITATION_AUDIO_ROUTE_PREFIX

router = APIRouter(prefix=MEDITATION_AUDIO_ROUTE_PREFIX, tags=["media"])

_AUDIO_KEY_PATTERN = re.compile(r"^[0-9a-f]{32}\.mp3$")

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio not found")


@router.get("/{key}", response_model=None)
async def get_meditation_audio(
    key: str,
    storage: AudioStorage = Depends(get_audio_storage),
) -> Response:
    if not _AUDIO_KEY_PATTERN.fullmatch(key) or not await storage.exists(key):
        raise _NOT_FOUND

    if isinstance(storage, S3AudioStorage):
        return RedirectResponse(
            storage.presigned_url(key), status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )
    if isinstance(storage, LocalAudioStorage):
        return FileResponse(storage.path_for(key), media_type=AUDIO_CONTENT_TYPE)
    raise _NOT_FOUND
