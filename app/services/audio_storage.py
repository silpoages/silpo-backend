import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import boto3
from botocore.exceptions import ClientError
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.enums import AudioStorageBackend

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

AUDIO_CONTENT_TYPE = "audio/mpeg"


class AudioStorage(Protocol):
    async def save(self, key: str, data: bytes) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...


class LocalAudioStorage:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

    def path_for(self, key: str) -> Path:
        return self.base_dir / key

    async def save(self, key: str, data: bytes) -> None:
        await run_in_threadpool(self._save_sync, key, data)

    def _save_sync(self, key: str, data: bytes) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=self.base_dir, suffix=".part")
        try:
            with os.fdopen(fd, "wb") as tmp_file:
                tmp_file.write(data)
            os.replace(tmp_path, self.path_for(key))
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise

    async def delete(self, key: str) -> None:
        await run_in_threadpool(self.path_for(key).unlink, missing_ok=True)

    async def exists(self, key: str) -> bool:
        return await run_in_threadpool(self.path_for(key).is_file)


class S3AudioStorage:
    def __init__(
        self,
        bucket: str,
        prefix: str,
        client: "S3Client",
        presigned_url_expire_seconds: int,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix
        self.client = client
        self.presigned_url_expire_seconds = presigned_url_expire_seconds

    def object_key(self, key: str) -> str:
        return f"{self.prefix}{key}"

    async def save(self, key: str, data: bytes) -> None:
        await run_in_threadpool(
            self.client.put_object,
            Bucket=self.bucket,
            Key=self.object_key(key),
            Body=data,
            ContentType=AUDIO_CONTENT_TYPE,
        )

    async def delete(self, key: str) -> None:
        await run_in_threadpool(
            self.client.delete_object, Bucket=self.bucket, Key=self.object_key(key)
        )

    async def exists(self, key: str) -> bool:
        try:
            await run_in_threadpool(
                self.client.head_object, Bucket=self.bucket, Key=self.object_key(key)
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True

    def presigned_url(self, key: str) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": self.object_key(key)},
            ExpiresIn=self.presigned_url_expire_seconds,
        )


def build_audio_storage(settings: Settings) -> AudioStorage:
    if settings.audio_storage_backend == AudioStorageBackend.S3:
        if not settings.audio_s3_bucket:
            raise RuntimeError("AUDIO_S3_BUCKET must be set when AUDIO_STORAGE_BACKEND=s3")
        client = boto3.client("s3", region_name=settings.audio_s3_region)
        return S3AudioStorage(
            bucket=settings.audio_s3_bucket,
            prefix=settings.audio_s3_prefix,
            client=client,
            presigned_url_expire_seconds=settings.audio_s3_presigned_url_expire_seconds,
        )
    return LocalAudioStorage(settings.audio_storage_local_dir)


@lru_cache
def _cached_audio_storage() -> AudioStorage:
    return build_audio_storage(get_settings())


def get_audio_storage() -> AudioStorage:
    return _cached_audio_storage()
