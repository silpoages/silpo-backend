import uuid
from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from moto import mock_aws

from app.core.config import Settings
from app.enums import AudioStorageBackend
from app.services import image_storage as image_storage_module
from app.services.image_storage import (
    LocalImageStorage,
    S3ImageStorage,
    build_image_storage,
    content_type_for_key,
    image_owner_id,
    new_image_key,
)

BUCKET = "silpo-diary-test"


@pytest.fixture
def s3_images(monkeypatch: pytest.MonkeyPatch) -> Iterator[S3ImageStorage]:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-2")
        client.create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "us-east-2"}
        )
        yield S3ImageStorage(bucket=BUCKET, prefix="diary/", client=client)


def _stubbed_storage() -> tuple[S3ImageStorage, Stubber]:
    client = boto3.client(
        "s3", region_name="us-east-2", aws_access_key_id="test", aws_secret_access_key="test"
    )
    return S3ImageStorage(bucket=BUCKET, prefix="diary/", client=client), Stubber(client)


async def test_s3_image_round_trip(s3_images: S3ImageStorage) -> None:
    key = new_image_key(uuid.uuid4(), "png")

    assert await s3_images.exists(key) is False
    assert await s3_images.read(key) is None

    await s3_images.save(key, b"\x89PNG\r\n\x1a\nbytes", "image/png")

    assert await s3_images.exists(key) is True
    assert await s3_images.read(key) == b"\x89PNG\r\n\x1a\nbytes"
    stored = s3_images.client.head_object(Bucket=BUCKET, Key=f"diary/{key}")
    assert stored["ContentType"] == "image/png"

    await s3_images.delete(key)

    assert await s3_images.exists(key) is False


async def test_s3_image_delete_of_missing_key_is_not_an_error(s3_images: S3ImageStorage) -> None:
    await s3_images.delete(new_image_key(uuid.uuid4(), "jpg"))


@pytest.mark.parametrize("operation", ["head_object", "get_object"])
async def test_s3_image_errors_other_than_not_found_are_raised(operation: str) -> None:
    # Uma falha de permissão não pode virar "foto não existe": o erro sobe.
    storage, stubber = _stubbed_storage()
    key = new_image_key(uuid.uuid4(), "jpg")
    stubber.add_client_error(operation, service_error_code="AccessDenied", http_status_code=403)

    with stubber, pytest.raises(ClientError, match="AccessDenied"):
        if operation == "head_object":
            await storage.exists(key)
        else:
            await storage.read(key)


async def test_local_image_save_failure_leaves_no_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = LocalImageStorage(tmp_path)
    key = new_image_key(uuid.uuid4(), "jpg")

    def failing_replace(src: str, dst: Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(image_storage_module.os, "replace", failing_replace)

    with pytest.raises(OSError, match="disk full"):
        await storage.save(key, b"\xff\xd8\xffdata", "image/jpeg")

    assert list(tmp_path.rglob("*.part")) == []
    assert await storage.exists(key) is False


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (f"{uuid.uuid4()}/{'a' * 32}.jpg", "image/jpeg"),
        (f"{uuid.uuid4()}/{'a' * 32}.jpeg", "image/jpeg"),
        (f"{uuid.uuid4()}/{'a' * 32}.png", "image/png"),
        (f"{uuid.uuid4()}/{'a' * 32}.webp", "image/webp"),
        (f"{uuid.uuid4()}/{'a' * 32}.gif", "application/octet-stream"),
        ("../etc/passwd", "application/octet-stream"),
    ],
)
def test_content_type_for_key(key: str, expected: str) -> None:
    assert content_type_for_key(key) == expected


@pytest.mark.parametrize(
    "key",
    [
        "not-a-key",
        f"{uuid.uuid4()}/short.jpg",
        f"{uuid.uuid4()}/{'a' * 32}.exe",
        f"../{uuid.uuid4()}/{'a' * 32}.jpg",
        f"{uuid.uuid4()}/{'A' * 32}.jpg",
    ],
)
def test_image_owner_id_rejects_keys_that_are_not_uploaded_images(key: str) -> None:
    assert image_owner_id(key) is None


def test_image_owner_id_reads_the_owner_from_a_generated_key() -> None:
    owner = uuid.uuid4()

    assert image_owner_id(new_image_key(owner, "webp")) == owner


def test_build_image_storage_requires_bucket_for_s3() -> None:
    settings = Settings(audio_storage_backend=AudioStorageBackend.S3, audio_s3_bucket="")

    with pytest.raises(RuntimeError, match="AUDIO_S3_BUCKET"):
        build_image_storage(settings)


def test_build_image_storage_uses_s3_with_the_diary_prefix() -> None:
    settings = Settings(
        audio_storage_backend=AudioStorageBackend.S3,
        audio_s3_bucket=BUCKET,
        audio_s3_region="us-east-2",
        diary_image_s3_prefix="diary-images/",
    )

    storage = build_image_storage(settings)

    assert isinstance(storage, S3ImageStorage)
    assert storage.bucket == BUCKET
    assert storage.object_key("a.jpg") == "diary-images/a.jpg"


def test_build_image_storage_defaults_to_local(tmp_path: Path) -> None:
    settings = Settings(
        audio_storage_backend=AudioStorageBackend.LOCAL, diary_image_local_dir=str(tmp_path)
    )

    storage = build_image_storage(settings)

    assert isinstance(storage, LocalImageStorage)
    assert storage.path_for("a.jpg") == tmp_path / "a.jpg"
