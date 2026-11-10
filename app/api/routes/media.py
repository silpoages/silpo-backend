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

# Only names the API itself generates (see build_audio_key), which also rules out any path
# traversal through the URL.
_AUDIO_KEY_PATTERN = re.compile(r"^[0-9a-f]{32}\.mp3$")

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio not found")


# Public on purpose: the app's audio player loads this URL directly, without the Bearer
# header. File names are random 128-bit identifiers, so they can't be enumerated.
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
        # FileResponse handles Range requests, so players can seek/stream.
        return FileResponse(storage.path_for(key), media_type=AUDIO_CONTENT_TYPE)
    raise _NOT_FOUND
