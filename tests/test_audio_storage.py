import uuid
from pathlib import Path

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from httpx import AsyncClient

from app.core.config import Settings
from app.enums import AudioStorageBackend
from app.main import app
from app.services import audio_storage as audio_storage_module
from app.services.audio_storage import (
    LocalAudioStorage,
    S3AudioStorage,
    build_audio_storage,
    get_audio_storage,
)


async def test_local_audio_save_failure_leaves_no_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = LocalAudioStorage(tmp_path)
    key = f"{uuid.uuid4().hex}.mp3"

    def failing_replace(src: str, dst: Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(audio_storage_module.os, "replace", failing_replace)

    with pytest.raises(OSError, match="disk full"):
        await storage.save(key, b"audio")

    assert list(tmp_path.iterdir()) == []
    assert await storage.exists(key) is False


async def test_s3_audio_exists_raises_errors_other_than_not_found() -> None:
    client = boto3.client(
        "s3", region_name="us-east-2", aws_access_key_id="test", aws_secret_access_key="test"
    )
    storage = S3AudioStorage(
        bucket="bucket", prefix="meditations/", client=client, presigned_url_expire_seconds=60
    )

    with Stubber(client) as stubber:
        stubber.add_client_error(
            "head_object", service_error_code="AccessDenied", http_status_code=403
        )
        with pytest.raises(ClientError, match="AccessDenied"):
            await storage.exists(f"{uuid.uuid4().hex}.mp3")


def test_build_audio_storage_uses_s3_when_configured() -> None:
    settings = Settings(
        audio_storage_backend=AudioStorageBackend.S3,
        audio_s3_bucket="silpo-audio",
        audio_s3_prefix="audio/",
        audio_s3_presigned_url_expire_seconds=120,
    )

    storage = build_audio_storage(settings)

    assert isinstance(storage, S3AudioStorage)
    assert storage.bucket == "silpo-audio"
    assert storage.object_key("a.mp3") == "audio/a.mp3"
    assert storage.presigned_url_expire_seconds == 120


class _UnknownStorage:
    """Um backend que a rota de mídia não sabe servir."""

    async def save(self, key: str, data: bytes) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool:
        return True


async def test_media_route_answers_404_for_a_backend_it_cannot_serve(client: AsyncClient) -> None:
    app.dependency_overrides[get_audio_storage] = _UnknownStorage

    response = await client.get(f"/media/meditations/{uuid.uuid4().hex}.mp3")

    assert response.status_code == 404
    assert response.json() == {"detail": "Audio not found"}


async def test_media_route_rejects_keys_outside_the_audio_pattern(
    client: AsyncClient, tmp_path: Path
) -> None:
    (tmp_path / "secret.txt").write_text("nope")
    app.dependency_overrides[get_audio_storage] = lambda: LocalAudioStorage(tmp_path)

    response = await client.get("/media/meditations/secret.txt")

    assert response.status_code == 404
