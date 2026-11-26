import io

import pytest
from fastapi import HTTPException, UploadFile

from app.services import image_validation, mp3_validation
from app.services.image_validation import image_extension, read_validated_image
from app.services.mp3_validation import (
    _frame_length,
    _parse_header,
    is_mp3,
    read_validated_mp3,
)

# Cabeçalho MPEG-1 Layer III, 128 kbps, 44,1 kHz: quadros de 417 bytes.
_MPEG1_L3 = bytes([0xFF, 0xFB, 0x90, 0x00])
# MPEG-1 Layer I, 32 kbps, 44,1 kHz: (12 * 32000 // 44100) * 4 = 32 bytes.
_MPEG1_L1 = bytes([0xFF, 0xFF, 0x10, 0x00])
# MPEG-2 Layer III, 64 kbps, 22,05 kHz: 72 * 64000 // 22050 = 208 bytes.
_MPEG2_L3 = bytes([0xFF, 0xF3, 0x80, 0x00])


def _two_frames(header: bytes, frame_length: int) -> bytes:
    return header + bytes(frame_length - len(header)) + header


def _upload(data: bytes, filename: str = "file.bin", size: int | None = None) -> UploadFile:
    return UploadFile(
        io.BytesIO(data),
        filename=filename,
        size=size,
        headers={"content-type": "audio/mpeg"},  # type: ignore[arg-type]
    )


# --- imagens -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "extension"),
    [
        (b"\xff\xd8\xff\xe0rest", "jpg"),
        (b"\x89PNG\r\n\x1a\nrest", "png"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "webp"),
    ],
)
def test_image_extension_detects_the_format_by_content(data: bytes, extension: str) -> None:
    assert image_extension(data) == extension


@pytest.mark.parametrize(
    "data",
    [b"GIF89a....", b"RIFF\x00\x00\x00\x00WAVEfmt ", b"%PDF-1.7", b"\xff\xd8"],
    ids=["gif", "riff-not-webp", "pdf", "truncated-jpeg"],
)
def test_image_extension_rejects_other_formats(data: bytes) -> None:
    with pytest.raises(HTTPException) as exc_info:
        image_extension(data)

    assert exc_info.value.status_code == 415


async def test_read_validated_image_returns_bytes_and_extension() -> None:
    data = b"RIFF\x00\x00\x00\x00WEBPVP8 data"

    assert await read_validated_image(_upload(data)) == (data, "webp")


async def test_read_validated_image_rejects_empty_file() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await read_validated_image(_upload(b""))

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Image file is empty"


async def test_read_validated_image_rejects_declared_size_over_limit() -> None:
    upload = _upload(b"\xff\xd8\xff", size=image_validation.MAX_IMAGE_SIZE_BYTES + 1)

    with pytest.raises(HTTPException) as exc_info:
        await read_validated_image(upload)

    assert exc_info.value.status_code == 413


async def test_read_validated_image_rejects_stream_over_limit_without_declared_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Sem Content-Length confiável, o limite é aplicado enquanto o arquivo é lido.
    monkeypatch.setattr(image_validation, "MAX_IMAGE_SIZE_BYTES", 10)
    monkeypatch.setattr(image_validation, "_READ_CHUNK_SIZE", 4)

    with pytest.raises(HTTPException) as exc_info:
        await read_validated_image(_upload(b"\xff\xd8\xff" + bytes(20)))

    assert exc_info.value.status_code == 413


async def test_read_validated_image_accepts_file_exactly_at_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(image_validation, "MAX_IMAGE_SIZE_BYTES", 10)
    monkeypatch.setattr(image_validation, "_READ_CHUNK_SIZE", 4)
    data = b"\xff\xd8\xff" + bytes(7)

    assert await read_validated_image(_upload(data)) == (data, "jpg")


# --- MP3 ---------------------------------------------------------------------------------


async def test_read_validated_mp3_rejects_stream_over_limit_without_declared_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mp3_validation, "MAX_AUDIO_SIZE_BYTES", 8)
    monkeypatch.setattr(mp3_validation, "_READ_CHUNK_SIZE", 4)

    with pytest.raises(HTTPException) as exc_info:
        await read_validated_mp3(_upload(_MPEG1_L3 + bytes(10), filename="a.mp3"))

    assert exc_info.value.status_code == 413


@pytest.mark.parametrize(
    ("header", "frame_length"),
    [(_MPEG1_L1, 32), (_MPEG2_L3, 208), (_MPEG1_L3, 417)],
    ids=["mpeg1-layer1", "mpeg2-layer3", "mpeg1-layer3"],
)
def test_is_mp3_finds_the_next_frame_at_the_computed_length(
    header: bytes, frame_length: int
) -> None:
    assert _frame_length(_two_frames(header, frame_length), 0) == frame_length
    assert is_mp3(_two_frames(header, frame_length)) is True
    # Um byte a mais e o segundo cabeçalho não está onde o primeiro diz: não é MP3.
    assert is_mp3(_two_frames(header, frame_length + 1)) is False


def test_is_mp3_rejects_id3_tag_with_invalid_syncsafe_size() -> None:
    # Cada byte do tamanho no ID3v2 só usa 7 bits; o bit alto ligado é um tag corrompido.
    tag = b"ID3\x04\x00\x00" + bytes([0x80, 0x00, 0x00, 0x00])

    assert is_mp3(tag + _two_frames(_MPEG1_L3, 417)) is False


@pytest.mark.parametrize(
    "header",
    [
        bytes([0xFF, 0xEB, 0x90, 0x00]),  # versão reservada (01)
        bytes([0xFF, 0xF9, 0x90, 0x00]),  # layer reservado (00)
        bytes([0xFF, 0xFB, 0x00, 0x00]),  # bitrate "free"
        bytes([0xFF, 0xFB, 0xF0, 0x00]),  # bitrate inválido
        bytes([0xFF, 0xFB, 0x9C, 0x00]),  # taxa de amostragem reservada
        bytes([0xFF, 0xFB, 0x90, 0x02]),  # ênfase reservada
    ],
    ids=["version", "layer", "free-bitrate", "bad-bitrate", "sample-rate", "emphasis"],
)
def test_parse_header_rejects_reserved_values(header: bytes) -> None:
    assert _parse_header(header, 0) is None
    assert is_mp3(header * 200) is False


def test_parse_header_rejects_positions_outside_the_data() -> None:
    assert _parse_header(_MPEG1_L3, -1) is None
    assert _parse_header(_MPEG1_L3, 1) is None


def test_frame_length_is_zero_when_there_is_no_header() -> None:
    assert _frame_length(bytes(8), 0) == 0
