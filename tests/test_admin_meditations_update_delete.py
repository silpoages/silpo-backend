import uuid
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ActivityType, Role
from app.main import app
from app.models.activity_session import ActivitySession
from app.models.meditation_activity import MeditationActivity
from app.models.user import User
from app.services.audio_storage import LocalAudioStorage, get_audio_storage
from app.services.meditation import build_audio_key, build_audio_url
from app.services.mp3_validation import MAX_AUDIO_SIZE_BYTES

URL = "/admin/meditations"
API_BASE_URL = "http://localhost:8000"
EXTERNAL_AUDIO_URL = "https://example.com/legacy.mp3"

_FRAME_HEADER = bytes([0xFF, 0xFB, 0x90, 0x00])
_FRAME_LENGTH = 417


def make_mp3(frames: int = 20) -> bytes:
    frame = _FRAME_HEADER + bytes(_FRAME_LENGTH - len(_FRAME_HEADER))
    return frame * frames


# Different sizes so a test can tell which of the two files is stored.
OLD_AUDIO = make_mp3(frames=10)
NEW_AUDIO = make_mp3(frames=30)


@pytest.fixture
def local_storage(tmp_path: Path) -> Iterator[LocalAudioStorage]:
    storage = LocalAudioStorage(tmp_path / "media")
    app.dependency_overrides[get_audio_storage] = lambda: storage
    yield storage
    app.dependency_overrides.pop(get_audio_storage, None)


@pytest_asyncio.fixture
async def admin_headers(
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> dict[str, str]:
    admin = await create_user(role=Role.ADMIN)
    return auth_headers(admin.id)


def audio_file(
    content: bytes | None = None,
    filename: str = "nova.mp3",
    content_type: str = "audio/mpeg",
) -> dict[str, tuple[str, bytes, str]]:
    return {"audio": (filename, NEW_AUDIO if content is None else content, content_type)}


def stored_names(storage: LocalAudioStorage) -> set[str]:
    if not storage.base_dir.exists():
        return set()
    return {path.name for path in storage.base_dir.iterdir()}


def key_from_url(audio_url: str) -> str:
    return audio_url.rsplit("/", 1)[1]


async def insert_meditation(db_session: AsyncSession, **overrides: Any) -> MeditationActivity:
    defaults: dict[str, Any] = {
        "name": "Meditação original",
        "description": "Descrição original",
        "audio_url": EXTERNAL_AUDIO_URL,
        "max_duration_seconds": 300,
        "enabled": True,
    }
    defaults.update(overrides)
    meditation = MeditationActivity(**defaults)
    db_session.add(meditation)
    await db_session.commit()
    await db_session.refresh(meditation)
    return meditation


async def seed_meditation(
    db_session: AsyncSession, storage: LocalAudioStorage, **overrides: Any
) -> tuple[MeditationActivity, str, str]:
    """Create a meditation whose audio file really exists in storage.

    Returns the meditation plus its original audio_url and storage key, captured up front
    because the test session is shared with the API and the instance is mutated in place.
    """
    key = build_audio_key()
    await storage.save(key, OLD_AUDIO)
    meditation = await insert_meditation(db_session, audio_url=build_audio_url(key), **overrides)
    return meditation, build_audio_url(key), key


async def fetch_meditation(
    db_session: AsyncSession, meditation_id: uuid.UUID
) -> MeditationActivity:
    result = await db_session.execute(
        select(MeditationActivity)
        .where(MeditationActivity.id == meditation_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


async def test_patch_meditation_requires_authentication(client: AsyncClient) -> None:
    response = await client.patch(f"{URL}/{uuid.uuid4()}", data={"name": "Novo"})

    assert response.status_code == 401


async def test_delete_meditation_requires_authentication(client: AsyncClient) -> None:
    response = await client.delete(f"{URL}/{uuid.uuid4()}")

    assert response.status_code == 401


async def test_patch_meditation_forbidden_for_non_admin(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user(role=Role.USER)
    meditation, _, key = await seed_meditation(db_session, local_storage)

    response = await client.patch(
        f"{URL}/{meditation.id}",
        data={"name": "Hackeada"},
        files=audio_file(),
        headers=auth_headers(user.id),
    )

    assert response.status_code == 403
    assert (await fetch_meditation(db_session, meditation.id)).name == "Meditação original"
    assert stored_names(local_storage) == {key}


async def test_delete_meditation_forbidden_for_non_admin(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user(role=Role.USER)
    meditation, _, _ = await seed_meditation(db_session, local_storage)

    response = await client.delete(f"{URL}/{meditation.id}", headers=auth_headers(user.id))

    assert response.status_code == 403
    assert (await fetch_meditation(db_session, meditation.id)).deleted_at is None


# ---------------------------------------------------------------------------
# PATCH: fields only (audio is preserved)
# ---------------------------------------------------------------------------


async def test_patch_meditation_updates_fields_and_keeps_audio(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    admin_headers: dict[str, str],
) -> None:
    meditation, old_url, old_key = await seed_meditation(db_session, local_storage)

    response = await client.patch(
        f"{URL}/{meditation.id}",
        data={
            "name": "Meditação atualizada",
            "description": "Nova descrição",
            "max_duration_seconds": "600",
            "enabled": "false",
        },
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": str(meditation.id),
        "name": "Meditação atualizada",
        "description": "Nova descrição",
        "audio_url": old_url,
        "max_duration_seconds": 600,
        "enabled": False,
    }

    saved = await fetch_meditation(db_session, meditation.id)
    assert saved.name == "Meditação atualizada"
    assert saved.description == "Nova descrição"
    assert saved.max_duration_seconds == 600
    assert saved.enabled is False
    assert saved.audio_url == old_url
    assert stored_names(local_storage) == {old_key}
    assert local_storage.path_for(old_key).read_bytes() == OLD_AUDIO


async def test_patch_meditation_partial_update_keeps_other_fields(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    admin_headers: dict[str, str],
) -> None:
    meditation, old_url, _ = await seed_meditation(db_session, local_storage)

    response = await client.patch(
        f"{URL}/{meditation.id}",
        data={"description": "Só a descrição mudou"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    saved = await fetch_meditation(db_session, meditation.id)
    assert saved.description == "Só a descrição mudou"
    assert saved.name == "Meditação original"
    assert saved.max_duration_seconds == 300
    assert saved.enabled is True
    assert saved.audio_url == old_url


async def test_patch_meditation_strips_whitespace(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    admin_headers: dict[str, str],
) -> None:
    meditation, _, _ = await seed_meditation(db_session, local_storage)

    response = await client.patch(
        f"{URL}/{meditation.id}", data={"name": "  Com espaços  "}, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Com espaços"


async def test_patch_meditation_ignores_audio_url_sent_by_client(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    admin_headers: dict[str, str],
) -> None:
    meditation, old_url, _ = await seed_meditation(db_session, local_storage)

    response = await client.patch(
        f"{URL}/{meditation.id}",
        data={"name": "Novo nome", "audio_url": "https://evil.example.com/a.mp3"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    saved = await fetch_meditation(db_session, meditation.id)
    assert saved.name == "Novo nome"
    assert saved.audio_url == old_url


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 81},
        {"description": ""},
        {"description": "x" * 301},
        {"max_duration_seconds": ""},
        {"max_duration_seconds": "0"},
        {"max_duration_seconds": "abc"},
        {"max_duration_seconds": "2147483648"},
        {"enabled": ""},
        {"enabled": "talvez"},
    ],
)
async def test_patch_meditation_rejects_invalid_fields_without_touching_audio(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    admin_headers: dict[str, str],
    overrides: dict[str, str],
) -> None:
    meditation, old_url, old_key = await seed_meditation(db_session, local_storage)

    response = await client.patch(
        f"{URL}/{meditation.id}", data=overrides, files=audio_file(), headers=admin_headers
    )

    assert response.status_code == 422
    saved = await fetch_meditation(db_session, meditation.id)
    assert saved.name == "Meditação original"
    assert saved.audio_url == old_url
    assert stored_names(local_storage) == {old_key}


# ---------------------------------------------------------------------------
# PATCH: audio replacement
# ---------------------------------------------------------------------------


async def test_patch_meditation_replaces_audio_and_removes_old_file(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    admin_headers: dict[str, str],
) -> None:
    meditation, old_url, old_key = await seed_meditation(db_session, local_storage)

    response = await client.patch(
        f"{URL}/{meditation.id}", files=audio_file(), headers=admin_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["audio_url"] != old_url
    assert body["audio_url"].startswith(f"{API_BASE_URL}/media/meditations/")
    new_key = key_from_url(body["audio_url"])
    assert new_key != old_key

    assert stored_names(local_storage) == {new_key}
    assert local_storage.path_for(new_key).read_bytes() == NEW_AUDIO

    saved = await fetch_meditation(db_session, meditation.id)
    assert saved.audio_url == body["audio_url"]
    assert saved.name == "Meditação original"
    assert saved.max_duration_seconds == 300
    assert saved.enabled is True


async def test_patch_meditation_replaced_audio_is_playable(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    admin_headers: dict[str, str],
) -> None:
    meditation, old_url, _ = await seed_meditation(db_session, local_storage)

    response = await client.patch(
        f"{URL}/{meditation.id}", files=audio_file(), headers=admin_headers
    )

    new_path = response.json()["audio_url"].removeprefix(API_BASE_URL)
    played = await client.get(new_path)
    assert played.status_code == 200
    assert played.headers["content-type"] == "audio/mpeg"
    assert played.content == NEW_AUDIO

    old_path = old_url.removeprefix(API_BASE_URL)
    assert (await client.get(old_path)).status_code == 404


async def test_patch_meditation_replaces_audio_and_updates_fields_together(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    admin_headers: dict[str, str],
) -> None:
    meditation, _, _ = await seed_meditation(db_session, local_storage)

    response = await client.patch(
        f"{URL}/{meditation.id}",
        data={"name": "Nome novo", "enabled": "false"},
        files=audio_file(),
        headers=admin_headers,
    )

    assert response.status_code == 200
    saved = await fetch_meditation(db_session, meditation.id)
    assert saved.name == "Nome novo"
    assert saved.enabled is False
    assert saved.description == "Descrição original"
    new_key = key_from_url(saved.audio_url)
    assert stored_names(local_storage) == {new_key}


async def test_patch_meditation_replaces_legacy_external_audio_url(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    admin_headers: dict[str, str],
) -> None:
    meditation = await insert_meditation(db_session, audio_url=EXTERNAL_AUDIO_URL)

    response = await client.patch(
        f"{URL}/{meditation.id}", files=audio_file(), headers=admin_headers
    )

    assert response.status_code == 200
    new_key = key_from_url(response.json()["audio_url"])
    assert stored_names(local_storage) == {new_key}


@pytest.mark.parametrize(
    ("files", "expected_status"),
    [
        (audio_file(filename="nova.wav"), 415),
        (audio_file(filename="nova"), 415),
        (audio_file(content_type="image/png"), 415),
        (audio_file(content=b"not really an mp3 file at all" * 100), 415),
        (audio_file(content=b"RIFF" + bytes(4000), filename="fake.mp3"), 415),
        (audio_file(content=b""), 422),
        (audio_file(content=bytes(MAX_AUDIO_SIZE_BYTES + 1)), 413),
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
async def test_patch_meditation_rejects_invalid_audio_and_keeps_current_one(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    admin_headers: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
    expected_status: int,
) -> None:
    meditation, old_url, old_key = await seed_meditation(db_session, local_storage)

    response = await client.patch(
        f"{URL}/{meditation.id}",
        data={"name": "Não deve salvar"},
        files=files,
        headers=admin_headers,
    )

    assert response.status_code == expected_status
    saved = await fetch_meditation(db_session, meditation.id)
    assert saved.name == "Meditação original"
    assert saved.audio_url == old_url
    assert stored_names(local_storage) == {old_key}
    assert local_storage.path_for(old_key).read_bytes() == OLD_AUDIO


async def test_patch_meditation_database_failure_keeps_old_audio_and_removes_new_file(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meditation, old_url, old_key = await seed_meditation(db_session, local_storage)
    meditation_id = meditation.id

    async def failing_commit() -> None:
        raise RuntimeError("database is down")

    monkeypatch.setattr(db_session, "commit", failing_commit)

    with pytest.raises(RuntimeError, match="database is down"):
        await client.patch(
            f"{URL}/{meditation_id}",
            data={"name": "Não deve persistir"},
            files=audio_file(),
            headers=admin_headers,
        )

    assert stored_names(local_storage) == {old_key}
    assert local_storage.path_for(old_key).read_bytes() == OLD_AUDIO

    monkeypatch.undo()
    saved = await fetch_meditation(db_session, meditation_id)
    assert saved.name == "Meditação original"
    assert saved.audio_url == old_url


async def test_patch_meditation_storage_failure_keeps_record_and_old_audio(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meditation, old_url, old_key = await seed_meditation(db_session, local_storage)
    meditation_id = meditation.id

    async def failing_save(key: str, data: bytes) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(local_storage, "save", failing_save)

    with pytest.raises(OSError, match="disk full"):
        await client.patch(
            f"{URL}/{meditation_id}",
            data={"name": "Não deve persistir"},
            files=audio_file(),
            headers=admin_headers,
        )

    saved = await fetch_meditation(db_session, meditation_id)
    assert saved.name == "Meditação original"
    assert saved.audio_url == old_url
    assert stored_names(local_storage) == {old_key}


async def test_patch_meditation_succeeds_when_old_file_cannot_be_deleted(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meditation, old_url, _ = await seed_meditation(db_session, local_storage)

    async def failing_delete(key: str) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(local_storage, "delete", failing_delete)

    response = await client.patch(
        f"{URL}/{meditation.id}", files=audio_file(), headers=admin_headers
    )

    assert response.status_code == 200
    saved = await fetch_meditation(db_session, meditation.id)
    assert saved.audio_url != old_url
    assert local_storage.path_for(key_from_url(saved.audio_url)).read_bytes() == NEW_AUDIO


async def test_patch_meditation_failure_after_commit_keeps_new_audio(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meditation, old_url, _ = await seed_meditation(db_session, local_storage)
    meditation_id = meditation.id

    async def failing_refresh(self: AsyncSession, instance: Any, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("connection lost after commit")

    monkeypatch.setattr(AsyncSession, "refresh", failing_refresh)

    with pytest.raises(RuntimeError, match="connection lost after commit"):
        await client.patch(f"{URL}/{meditation_id}", files=audio_file(), headers=admin_headers)

    monkeypatch.undo()
    saved = await fetch_meditation(db_session, meditation_id)
    assert saved.audio_url != old_url
    assert stored_names(local_storage) == {key_from_url(saved.audio_url)}

async def test_patch_meditation_returns_404_when_not_found(
    client: AsyncClient,
    local_storage: LocalAudioStorage,
    admin_headers: dict[str, str],
) -> None:
    response = await client.patch(
        f"{URL}/{uuid.uuid4()}",
        data={"name": "Novo"},
        files=audio_file(),
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert stored_names(local_storage) == set()


async def test_patch_meditation_returns_404_when_soft_deleted(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    admin_headers: dict[str, str],
) -> None:
    meditation, _, key = await seed_meditation(
        db_session, local_storage, deleted_at=datetime.now(UTC), enabled=False
    )

    response = await client.patch(
        f"{URL}/{meditation.id}",
        data={"name": "Novo"},
        files=audio_file(),
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert (await fetch_meditation(db_session, meditation.id)).name == "Meditação original"
    assert stored_names(local_storage) == {key}


async def test_patch_meditation_returns_422_for_invalid_id(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.patch(f"{URL}/not-a-uuid", data={"name": "Novo"}, headers=admin_headers)

    assert response.status_code == 422


async def test_patch_meditation_hides_and_shows_in_app(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
    admin_headers: dict[str, str],
) -> None:
    user = await create_user()
    meditation, _, _ = await seed_meditation(db_session, local_storage)
    path = f"{URL}/{meditation.id}"

    async def app_ids() -> list[str]:
        response = await client.get("/activities", headers=auth_headers(user.id))
        return [item["id"] for item in response.json()["items"]]

    assert str(meditation.id) in await app_ids()

    hide = await client.patch(path, data={"enabled": "false"}, headers=admin_headers)
    assert hide.status_code == 200
    assert str(meditation.id) not in await app_ids()
    detail = await client.get(f"/activities/{meditation.id}", headers=auth_headers(user.id))
    assert detail.status_code == 404

    show = await client.patch(path, data={"enabled": "true"}, headers=admin_headers)
    assert show.status_code == 200
    assert str(meditation.id) in await app_ids()

async def test_delete_meditation_soft_deletes_and_keeps_row_and_audio(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    admin_headers: dict[str, str],
) -> None:
    meditation, old_url, key = await seed_meditation(db_session, local_storage)

    response = await client.delete(f"{URL}/{meditation.id}", headers=admin_headers)

    assert response.status_code == 204
    assert response.content == b""

    saved = await fetch_meditation(db_session, meditation.id)
    assert saved.deleted_at is not None
    assert saved.enabled is False
    assert saved.audio_url == old_url
    assert stored_names(local_storage) == {key}


async def test_delete_meditation_removes_it_from_app(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
    admin_headers: dict[str, str],
) -> None:
    user = await create_user()
    meditation, _, _ = await seed_meditation(db_session, local_storage)

    await client.delete(f"{URL}/{meditation.id}", headers=admin_headers)

    listing = await client.get("/activities", headers=auth_headers(user.id))
    assert str(meditation.id) not in [item["id"] for item in listing.json()["items"]]

    detail = await client.get(f"/activities/{meditation.id}", headers=auth_headers(user.id))
    assert detail.status_code == 404

    session = await client.post(
        f"/activities/{meditation.id}/sessions",
        json={"time_spent_seconds": 30},
        headers=auth_headers(user.id),
    )
    assert session.status_code == 404


async def test_delete_meditation_preserves_session_history(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    create_user: Callable[..., Awaitable[User]],
    admin_headers: dict[str, str],
) -> None:
    user = await create_user()
    meditation, _, _ = await seed_meditation(db_session, local_storage)
    db_session.add_all(
        [
            ActivitySession(
                user_id=user.id,
                activity_id=meditation.id,
                type=ActivityType.MEDITATION,
                time_spent_seconds=seconds,
                posted_at=datetime.now(UTC),
            )
            for seconds in (30, 60, 90)
        ]
    )
    await db_session.commit()

    response = await client.delete(f"{URL}/{meditation.id}", headers=admin_headers)

    assert response.status_code == 204
    count = await db_session.scalar(
        select(func.count())
        .select_from(ActivitySession)
        .where(ActivitySession.activity_id == meditation.id)
    )
    assert count == 3


async def test_delete_meditation_returns_404_when_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.delete(f"{URL}/{uuid.uuid4()}", headers=admin_headers)

    assert response.status_code == 404


async def test_delete_meditation_returns_404_when_already_deleted(
    client: AsyncClient,
    db_session: AsyncSession,
    local_storage: LocalAudioStorage,
    admin_headers: dict[str, str],
) -> None:
    meditation, _, _ = await seed_meditation(db_session, local_storage)
    path = f"{URL}/{meditation.id}"

    first = await client.delete(path, headers=admin_headers)
    second = await client.delete(path, headers=admin_headers)

    assert first.status_code == 204
    assert second.status_code == 404


async def test_delete_meditation_returns_422_for_invalid_id(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.delete(f"{URL}/not-a-uuid", headers=admin_headers)

    assert response.status_code == 422
