import logging
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Role
from app.models.activity import Activity
from app.models.meditation_activity import MeditationActivity
from app.models.user import User
from app.schemas.meditation import MeditationBase, MeditationCreate, MeditationUpdate
from app.services.audio_storage import LocalAudioStorage
from app.services.meditation import MeditationService

URL = "/admin/meditations"

CreateUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[[uuid.UUID], dict[str, str]]


@pytest_asyncio.fixture
async def marker(db_session: AsyncSession) -> AsyncGenerator[str, None]:
    value = f"Lista {uuid.uuid4().hex[:12]}"
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
async def admin_headers(create_user: CreateUser, auth_headers: AuthHeaders) -> dict[str, str]:
    admin = await create_user(role=Role.ADMIN)
    return auth_headers(admin.id)


async def _create(
    db_session: AsyncSession, name: str, *, enabled: bool = True, description: str = "Calma."
) -> MeditationActivity:
    return await MeditationService(db_session).create(
        MeditationCreate(
            name=name,
            description=description,
            audio_url="https://cdn.example.com/a.mp3",
            max_duration_seconds=300,
            enabled=enabled,
        )
    )


async def test_list_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(URL)).status_code == 401


async def test_list_forbidden_for_non_admin(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders
) -> None:
    user = await create_user()

    response = await client.get(URL, headers=auth_headers(user.id))

    assert response.status_code == 403


async def test_list_searches_name_and_description_case_insensitive(
    client: AsyncClient, db_session: AsyncSession, marker: str, admin_headers: dict[str, str]
) -> None:
    by_name = await _create(db_session, f"{marker} sono")
    by_description = await _create(
        db_session, f"{marker} foco", description=f"Para {marker.upper()} dormir"
    )
    await _create(db_session, "Outra meditação qualquer")

    response = await client.get(URL, params={"search": f"  {marker}  "}, headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {item["id"] for item in body["items"]} == {str(by_name.id), str(by_description.id)}
    assert body["page"] == 1
    assert body["page_size"] == 20


async def test_list_filters_by_enabled_and_hides_deleted(
    client: AsyncClient, db_session: AsyncSession, marker: str, admin_headers: dict[str, str]
) -> None:
    visible = await _create(db_session, f"{marker} ativa")
    hidden = await _create(db_session, f"{marker} oculta", enabled=False)
    deleted = await _create(db_session, f"{marker} removida")
    await MeditationService(db_session).delete(deleted.id)

    async def ids(**params: object) -> set[str]:
        response = await client.get(URL, params={"search": marker, **params}, headers=admin_headers)
        assert response.status_code == 200
        return {item["id"] for item in response.json()["items"]}

    assert await ids() == {str(visible.id), str(hidden.id)}
    assert await ids(enabled="true") == {str(visible.id)}
    assert await ids(enabled="false") == {str(hidden.id)}


async def test_list_paginates_newest_first(
    client: AsyncClient, db_session: AsyncSession, marker: str, admin_headers: dict[str, str]
) -> None:
    created = [await _create(db_session, f"{marker} {index}") for index in range(3)]

    page_1 = await client.get(URL, params={"search": marker, "page_size": 2}, headers=admin_headers)
    page_2 = await client.get(
        URL, params={"search": marker, "page_size": 2, "page": 2}, headers=admin_headers
    )

    assert page_1.json()["total"] == 3
    assert [item["id"] for item in page_1.json()["items"]] == [
        str(created[2].id),
        str(created[1].id),
    ]
    assert [item["id"] for item in page_2.json()["items"]] == [str(created[0].id)]


async def test_list_without_search_includes_the_newest(
    client: AsyncClient, db_session: AsyncSession, marker: str, admin_headers: dict[str, str]
) -> None:
    newest = await _create(db_session, f"{marker} recente")

    response = await client.get(URL, params={"page_size": 100}, headers=admin_headers)

    assert response.json()["items"][0]["id"] == str(newest.id)


@pytest.mark.parametrize(
    "params",
    [{"page": 0}, {"page_size": 0}, {"page_size": 101}, {"search": "x" * 81}],
)
async def test_list_rejects_invalid_query(
    client: AsyncClient, admin_headers: dict[str, str], params: dict[str, object]
) -> None:
    response = await client.get(URL, params=params, headers=admin_headers)

    assert response.status_code == 422


# --- serviço -----------------------------------------------------------------------------


async def test_service_without_storage_cannot_upload_audio(db_session: AsyncSession) -> None:
    service = MeditationService(db_session)
    form = MeditationBase(name="Sem storage", description="x", max_duration_seconds=60)

    with pytest.raises(RuntimeError, match="needs an AudioStorage"):
        await service.create_with_audio(form, b"audio")
    with pytest.raises(RuntimeError, match="needs an AudioStorage"):
        await service.update_with_audio(uuid.uuid4(), MeditationUpdate(), b"audio")


async def test_service_without_storage_skips_audio_cleanup(db_session: AsyncSession) -> None:
    await MeditationService(db_session)._delete_audio_quietly(f"{uuid.uuid4().hex}.mp3")


async def test_insert_failure_is_raised_even_if_the_audio_cleanup_fails(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage = LocalAudioStorage(tmp_path)
    service = MeditationService(db_session, storage)
    monkeypatch.setattr(logging.getLogger("app.services.meditation"), "disabled", False)

    async def failing_insert(payload: MeditationCreate) -> MeditationActivity:
        raise RuntimeError("database is down")

    async def failing_delete(key: str) -> None:
        raise OSError("storage unreachable")

    monkeypatch.setattr(service, "_insert", failing_insert)
    monkeypatch.setattr(storage, "delete", failing_delete)
    form = MeditationBase(name="Falha dupla", description="x", max_duration_seconds=60)

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError, match="database is down"):
        await service.create_with_audio(form, b"audio")

    # O erro original sobe; a falha da limpeza só é registrada, e o arquivo órfão fica no log.
    assert "Failed to delete orphaned meditation audio" in caplog.text
    [orphan] = list(tmp_path.iterdir())
    assert orphan.name in caplog.text


async def test_get_enabled_returns_enabled_meditation(
    db_session: AsyncSession, marker: str
) -> None:
    meditation = await _create(db_session, f"{marker} habilitada")

    found = await MeditationService(db_session).get_enabled(meditation.id)

    assert found.id == meditation.id
