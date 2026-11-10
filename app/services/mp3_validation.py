from pathlib import PurePath

from fastapi import HTTPException, UploadFile, status

MAX_AUDIO_SIZE_BYTES = 20 * 1024 * 1024
ALLOWED_AUDIO_CONTENT_TYPES = frozenset(
    {"audio/mpeg", "audio/mp3", "audio/mpeg3", "audio/x-mpeg-3", "application/octet-stream"}
)
_READ_CHUNK_SIZE = 1024 * 1024
_FRAME_SEARCH_WINDOW = 64 * 1024


def _unsupported(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=detail)


async def read_validated_mp3(upload: UploadFile) -> bytes:
    filename = upload.filename or ""
    if PurePath(filename).suffix.lower() != ".mp3":
        raise _unsupported("Audio file must have the .mp3 extension")

    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_AUDIO_CONTENT_TYPES:
        raise _unsupported("Audio file must be an MP3 (audio/mpeg)")

    if upload.size is not None and upload.size > MAX_AUDIO_SIZE_BYTES:
        raise _too_large()

    data = bytearray()
    while chunk := await upload.read(_READ_CHUNK_SIZE):
        data.extend(chunk)
        if len(data) > MAX_AUDIO_SIZE_BYTES:
            raise _too_large()

    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Audio file is empty"
        )

    if not is_mp3(bytes(data)):
        raise _unsupported("Audio file content is not a valid MP3")

    return bytes(data)


def _too_large() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail=f"Audio file exceeds the {MAX_AUDIO_SIZE_BYTES // (1024 * 1024)} MB limit",
    )


def is_mp3(data: bytes) -> bool:
    offset = 0
    search_window = 1
    if data[:3] == b"ID3":
        if len(data) < 10:
            return False
        size_bytes = data[6:10]
        if any(byte & 0x80 for byte in size_bytes):
            return False
        tag_size = 0
        for byte in size_bytes:
            tag_size = (tag_size << 7) | byte
        has_footer = bool(data[5] & 0x10)
        offset = 10 + tag_size + (10 if has_footer else 0)
        search_window = _FRAME_SEARCH_WINDOW

    for position in range(offset, min(offset + search_window, len(data) - 3)):
        if not _is_frame_header(data, position):
            continue
        next_position = position + _frame_length(data, position)
        if next_position + 4 <= len(data):
            return _is_frame_header(data, next_position)
        return True
    return False


_BITRATES_KBPS = {
    (True, 1): [0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448],
    (True, 2): [0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384],
    (True, 3): [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    (False, 1): [0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256],
    (False, 2): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
    (False, 3): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}
_SAMPLE_RATES = {
    0b11: [44100, 48000, 32000],
    0b10: [22050, 24000, 16000],
    0b00: [11025, 12000, 8000],
}


def _parse_header(data: bytes, position: int) -> tuple[int, int, int, int, int] | None:
    if position < 0 or position + 4 > len(data):
        return None
    b1, b2, b3 = data[position + 1], data[position + 2], data[position + 3]
    if data[position] != 0xFF or (b1 & 0xE0) != 0xE0:
        return None
    version_bits = (b1 >> 3) & 0b11
    layer_bits = (b1 >> 1) & 0b11
    bitrate_index = (b2 >> 4) & 0b1111
    sample_rate_index = (b2 >> 2) & 0b11
    padding = (b2 >> 1) & 0b1
    if version_bits == 0b01 or layer_bits == 0b00:
        return None
    if bitrate_index in (0b0000, 0b1111) or sample_rate_index == 0b11:
        return None
    if b3 & 0b11 == 0b10:
        return None
    layer = 4 - layer_bits
    return version_bits, layer, bitrate_index, sample_rate_index, padding


def _is_frame_header(data: bytes, position: int) -> bool:
    return _parse_header(data, position) is not None


def _frame_length(data: bytes, position: int) -> int:
    header = _parse_header(data, position)
    if header is None:
        return 0
    version_bits, layer, bitrate_index, sample_rate_index, padding = header
    is_mpeg1 = version_bits == 0b11
    bitrate = _BITRATES_KBPS[(is_mpeg1, layer)][bitrate_index] * 1000
    sample_rate = _SAMPLE_RATES[version_bits][sample_rate_index]
    if layer == 1:
        return (12 * bitrate // sample_rate + padding) * 4
    if layer == 3 and not is_mpeg1:
        return 72 * bitrate // sample_rate + padding
    return 144 * bitrate // sample_rate + padding
