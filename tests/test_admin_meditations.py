import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any

import boto3
import pytest
import pytest_asyncio
from httpx import AsyncClient
from moto import mock_aws
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Role
from app.main import app
from app.models.activity import Activity
from app.models.meditation_activity import MeditationActivity
from app.models.user import User
from app.services.audio_storage import (
    LocalAudioStorage,
    S3AudioStorage,
    build_audio_storage,
    get_audio_storage,
)
from app.services.meditation import MeditationService
from app.services.mp3_validation import MAX_AUDIO_SIZE_BYTES, is_mp3

URL = "/admin/meditations"

_FRAME_HEADER = bytes([0xFF, 0xFB, 0x90, 0x00])
_FRAME_LENGTH = 417


def make_mp3(frames: int = 20, with_id3: bool = False) -> bytes:
    frame = _FRAME_HEADER + bytes(_FRAME_LENGTH - len(_FRAME_HEADER))
    audio = frame * frames
    if with_id3:
        tag_body = b"TIT2" + bytes(16)
        size = len(tag_body)
        syncsafe = bytes(
            [(size >> 21) & 0x7F, (size >> 14) & 0x7F, (size >> 7) & 0x7F, size & 0x7F]
        )
        audio = b"ID3" + bytes([4, 0, 0]) + syncsafe + tag_body + audio
    return audio


@pytest.fixture
def local_storage(tmp_path: Path) -> Iterator[LocalAudioStorage]:
    storage = LocalAudioStorage(tmp_path / "media")
    app.dependency_overrides[get_audio_storage] = lambda: storage
    yield storage
    app.dependency_overrides.pop(get_audio_storage, None)


@pytest_asyncio.fixture
async def marker(db_session: AsyncSession) -> AsyncGenerator[str, None]:
    value = f"Meditação {uuid.uuid4().hex[:12]}"
    yield value
    ids = (
        await db_session.scalars(
            select(MeditationActivity.id).where(MeditationActivity.name.startswith(value))
        )
    ).all()
    if ids:
        await db_session.execute(delete(MeditationActivity).where(MeditationActivity.id.in_(ids)))
        await db_session.execute(delete(Activity).where(Activity.id.in_(ids)))
        await db_session.commit()


@pytest_asyncio.fixture
async def admin_headers(
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> dict[str, str]:
    admin = await create_user(role=Role.ADMIN)
    return auth_headers(admin.id)


def form_data(marker: str, **overrides: Any) -> dict[str, str]:
    data = {
        "name": marker,
        "description": "Uma meditação guiada de 5 minutos.",
        "max_duration_seconds": "300",
        "enabled": "true",
    }
    data.update(overrides)
    return data


def audio_file(
    content: bytes | None = None,
    filename: str = "meditacao.mp3",
    content_type: str = "audio/mpeg",
) -> dict[str, tuple[str, bytes, str]]:
    return {"audio": (filename, make_mp3() if content is None else content, content_type)}


async def find_by_name(db_session: AsyncSession, name: str) -> list[MeditationActivity]:
    db_session.expire_all()
    result = await db_session.scalars(
        select(MeditationActivity).where(MeditationActivity.name == name)
    )
    return list(result.all())


def stored_files(storage: LocalAudioStorage) -> list[Path]:
    if not storage.base_dir.exists():
        return []
    return list(storage.base_dir.iterdir())


async def test_create_meditation_requires_authentication(
    client: AsyncClient, local_storage: LocalAudioStorage, marker: str
) -> None:
    response = await client.post(URL, data=form_data(marker), files=audio_file())

    assert response.status_code == 401
    assert stored_files(local_storage) == []


async def test_create_meditation_forbidden_for_non_admin(
    client: AsyncClient,
    local_storage: LocalAudioStorage,
    marker: str,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.post(
        URL, data=form_data(marker), files=audio_file(), headers=auth_headers(user.id)
    )

    assert response.status_code == 403
    assert stored_files(local_storage) == []


async def test_create_meditation_persists_record_and_audio(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    marker: str,
    admin_headers: dict[str, str],
) -> None:
    audio = make_mp3()

    response = await client.post(
        URL,
        data=form_data(f"  {marker}  ", enabled="false"),
        files=audio_file(audio),
        headers=admin_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "id",
        "name",
        "description",
        "audio_url",
        "max_duration_seconds",
        "enabled",
    }
    assert body["name"] == marker
    assert body["max_duration_seconds"] == 300
    assert body["enabled"] is False
    assert body["audio_url"].startswith("http://localhost:8000/media/meditations/")

    [record] = await find_by_name(db_session, marker)
    assert str(record.id) == body["id"]
    assert record.audio_url == body["audio_url"]

    key = body["audio_url"].rsplit("/", 1)[1]
    assert stored_files(local_storage) == [local_storage.path_for(key)]
    assert local_storage.path_for(key).read_bytes() == audio


async def test_created_meditation_audio_is_playable(
    client: AsyncClient,
    local_storage: LocalAudioStorage,
    marker: str,
    admin_headers: dict[str, str],
) -> None:
    audio = make_mp3()
    created = await client.post(
        URL, data=form_data(marker), files=audio_file(audio), headers=admin_headers
    )
    path = created.json()["audio_url"].removeprefix("http://localhost:8000")

    response = await client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == audio

    partial = await client.get(path, headers={"Range": "bytes=0-99"})
    assert partial.status_code == 206
    assert partial.content == audio[:100]


async def test_created_meditation_audio_survives_restart(
    client: AsyncClient,
    local_storage: LocalAudioStorage,
    marker: str,
    admin_headers: dict[str, str],
) -> None:
    audio = make_mp3()
    created = await client.post(
        URL, data=form_data(marker), files=audio_file(audio), headers=admin_headers
    )
    path = created.json()["audio_url"].removeprefix("http://localhost:8000")

    restarted = LocalAudioStorage(local_storage.base_dir)
    app.dependency_overrides[get_audio_storage] = lambda: restarted

    response = await client.get(path)

    assert response.status_code == 200
    assert response.content == audio


async def test_create_meditation_accepts_mp3_with_id3_tag(
    client: AsyncClient,
    local_storage: LocalAudioStorage,
    marker: str,
    admin_headers: dict[str, str],
) -> None:
    response = await client.post(
        URL,
        data=form_data(marker),
        files=audio_file(make_mp3(with_id3=True)),
        headers=admin_headers,
    )

    assert response.status_code == 201


async def test_create_meditation_accepts_file_at_size_limit(
    client: AsyncClient,
    local_storage: LocalAudioStorage,
    marker: str,
    admin_headers: dict[str, str],
) -> None:
    audio = make_mp3()
    audio += bytes(MAX_AUDIO_SIZE_BYTES - len(audio))

    response = await client.post(
        URL, data=form_data(marker), files=audio_file(audio), headers=admin_headers
    )

    assert response.status_code == 201


@pytest.mark.parametrize(
    ("files", "expected_status"),
    [
        (audio_file(filename="meditacao.wav"), 415),
        (audio_file(filename="meditacao"), 415),
        (audio_file(content_type="image/png"), 415),
        (audio_file(content=b"not really an mp3 file at all" * 100), 415),
        (audio_file(content=b"RIFF" + bytes(4000), filename="fake.mp3"), 415),
        (audio_file(content=b""), 422),
        (audio_file(content=make_mp3() + bytes(MAX_AUDIO_SIZE_BYTES)), 413),
    ],
    ids=[
        "wrong-extension",
        "no-extension",
        "wrong-content-type",
        "text-content",
        "wav-content",
        "empty",
        "too-large",
    ],
)
async def test_create_meditation_rejects_invalid_audio(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    marker: str,
    admin_headers: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
    expected_status: int,
) -> None:
    response = await client.post(URL, data=form_data(marker), files=files, headers=admin_headers)

    assert response.status_code == expected_status
    assert await find_by_name(db_session, marker) == []
    assert stored_files(local_storage) == []


async def test_create_meditation_requires_audio(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    marker: str,
    admin_headers: dict[str, str],
) -> None:
    response = await client.post(URL, data=form_data(marker), headers=admin_headers)

    assert response.status_code == 422
    assert await find_by_name(db_session, marker) == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "   "},
        {"name": "x" * 81},
        {"description": ""},
        {"description": "x" * 301},
        {"max_duration_seconds": "0"},
        {"max_duration_seconds": "abc"},
        {"enabled": "talvez"},
    ],
)
async def test_create_meditation_rejects_invalid_fields(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    marker: str,
    admin_headers: dict[str, str],
    overrides: dict[str, str],
) -> None:
    response = await client.post(
        URL, data=form_data(marker, **overrides), files=audio_file(), headers=admin_headers
    )

    assert response.status_code == 422
    assert stored_files(local_storage) == []


@pytest.mark.parametrize("missing", ["name", "description", "max_duration_seconds"])
async def test_create_meditation_rejects_missing_fields(
    client: AsyncClient,
    local_storage: LocalAudioStorage,
    marker: str,
    admin_headers: dict[str, str],
    missing: str,
) -> None:
    data = form_data(marker)
    del data[missing]

    response = await client.post(URL, data=data, files=audio_file(), headers=admin_headers)

    assert response.status_code == 422
    assert stored_files(local_storage) == []


async def test_create_meditation_defaults_to_enabled(
    client: AsyncClient,
    local_storage: LocalAudioStorage,
    marker: str,
    admin_headers: dict[str, str],
) -> None:
    data = form_data(marker)
    del data["enabled"]

    response = await client.post(URL, data=data, files=audio_file(), headers=admin_headers)

    assert response.status_code == 201
    assert response.json()["enabled"] is True


async def test_database_failure_removes_uploaded_audio(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    marker: str,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_create(self: MeditationService, payload: Any) -> MeditationActivity:
        raise RuntimeError("database is down")

    monkeypatch.setattr(MeditationService, "create", failing_create)

    with pytest.raises(RuntimeError, match="database is down"):
        await client.post(URL, data=form_data(marker), files=audio_file(), headers=admin_headers)

    assert stored_files(local_storage) == []
    assert await find_by_name(db_session, marker) == []


async def test_storage_failure_leaves_no_record(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    marker: str,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_save(key: str, data: bytes) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(local_storage, "save", failing_save)

    with pytest.raises(OSError, match="disk full"):
        await client.post(URL, data=form_data(marker), files=audio_file(), headers=admin_headers)

    assert await find_by_name(db_session, marker) == []


@pytest.mark.parametrize(
    "key",
    [
        f"{uuid.uuid4().hex}.mp3",
        "not-a-key.mp3",
        f"{uuid.uuid4().hex}.wav",
        "..%2F..%2Fetc%2Fpasswd",
    ],
)
async def test_get_meditation_audio_returns_404_for_unknown_key(
    client: AsyncClient, local_storage: LocalAudioStorage, key: str
) -> None:
    response = await client.get(f"/media/meditations/{key}")

    assert response.status_code == 404


@pytest.fixture
def s3_storage(monkeypatch: pytest.MonkeyPatch) -> Iterator[S3AudioStorage]:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-2")
        client.create_bucket(
            Bucket="silpo-audio-test",
            CreateBucketConfiguration={"LocationConstraint": "us-east-2"},
        )
        storage = S3AudioStorage(
            bucket="silpo-audio-test",
            prefix="meditations/",
            client=client,
            presigned_url_expire_seconds=60,
        )
        app.dependency_overrides[get_audio_storage] = lambda: storage
        yield storage
        app.dependency_overrides.pop(get_audio_storage, None)


async def test_s3_storage_upload_and_redirect(
    client: AsyncClient,
    s3_storage: S3AudioStorage,
    marker: str,
    admin_headers: dict[str, str],
) -> None:
    audio = make_mp3()

    created = await client.post(
        URL, data=form_data(marker), files=audio_file(audio), headers=admin_headers
    )

    assert created.status_code == 201
    key = created.json()["audio_url"].rsplit("/", 1)[1]
    stored = s3_storage.client.get_object(Bucket="silpo-audio-test", Key=f"meditations/{key}")
    assert stored["Body"].read() == audio
    assert stored["ContentType"] == "audio/mpeg"

    response = await client.get(f"/media/meditations/{key}")

    assert response.status_code == 307
    assert "silpo-audio-test" in response.headers["location"]
    assert f"meditations/{key}" in response.headers["location"]


async def test_s3_storage_delete_and_exists(s3_storage: S3AudioStorage) -> None:
    key = f"{uuid.uuid4().hex}.mp3"

    assert await s3_storage.exists(key) is False
    await s3_storage.save(key, b"data")
    assert await s3_storage.exists(key) is True
    await s3_storage.delete(key)
    assert await s3_storage.exists(key) is False


def test_build_audio_storage_requires_bucket_for_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import Settings

    with pytest.raises(RuntimeError, match="AUDIO_S3_BUCKET"):
        build_audio_storage(Settings(audio_storage_backend="s3", audio_s3_bucket=""))


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (make_mp3(), True),
        (make_mp3(frames=1), True),
        (make_mp3(with_id3=True), True),
        (b"ID3", False),
        (bytes([0xFF, 0xFB, 0x90, 0x00]) + b"garbage" * 100, False),
        (bytes([0xFF, 0xFF, 0xFF, 0xFF]) * 200, False),
        (b"\x00" + make_mp3(), False),
        (b"OggS" + bytes(1000), False),
    ],
    ids=[
        "frames",
        "single-frame",
        "id3",
        "truncated-id3",
        "lone-sync",
        "invalid-header",
        "offset",
        "ogg",
    ],
)
def test_is_mp3(data: bytes, expected: bool) -> None:
    assert is_mp3(data) is expected
