from fastapi import HTTPException, UploadFile, status

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
_READ_CHUNK_SIZE = 1024 * 1024

_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"
_WEBP_RIFF = b"RIFF"
_WEBP = b"WEBP"


def _unsupported(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=detail)


def _too_large() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail=f"Image file exceeds the {MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MB limit",
    )


def image_extension(data: bytes) -> str:
    if data.startswith(_JPEG):
        return "jpg"
    if data.startswith(_PNG):
        return "png"
    if data.startswith(_WEBP_RIFF) and data[8:12] == _WEBP:
        return "webp"
    raise _unsupported("Image file must be JPEG, PNG, or WebP")


async def read_validated_image(upload: UploadFile) -> tuple[bytes, str]:
    if upload.size is not None and upload.size > MAX_IMAGE_SIZE_BYTES:
        raise _too_large()

    data = bytearray()
    while chunk := await upload.read(_READ_CHUNK_SIZE):
        data.extend(chunk)
        if len(data) > MAX_IMAGE_SIZE_BYTES:
            raise _too_large()

    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Image file is empty"
        )

    extension = image_extension(bytes(data))
    return bytes(data), extension
