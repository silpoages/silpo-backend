import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.meditation_activity import MeditationActivity
from app.schemas.meditation import MeditationCreate, MeditationUpdate
from app.services.meditation import MeditationService

# Rotas administrativas ficam fora do escopo desta task; os testes aqui exercitam o
# MeditationService e os schemas diretamente, sem passar pela camada HTTP.

CreateMeditation = Callable[..., Awaitable[MeditationActivity]]


@pytest_asyncio.fixture
async def create_meditation(
    db_session: AsyncSession,
) -> AsyncGenerator[CreateMeditation, None]:
    created_ids: list[uuid.UUID] = []

    async def _create(**overrides: Any) -> MeditationActivity:
        defaults: dict[str, Any] = {
            "name": "Respiração consciente",
            "description": "Uma meditação guiada de 5 minutos.",
            "audio_url": "https://example.com/meditacao.mp3",
            "max_duration_seconds": 300,
        }
        defaults.update(overrides)
        meditation = await MeditationService(db_session).create(MeditationCreate(**defaults))
        created_ids.append(meditation.id)
        return meditation

    yield _create

    # Limpeza: apaga só o que este teste criou, para não interferir nos outros
    # arquivos de teste (o banco de testes é compartilhado entre todos os testes da
    # rodada). MeditationActivity usa joined-table inheritance, então a tabela filha
    # precisa ser apagada antes da "activity".
    await db_session.execute(
        delete(MeditationActivity).where(MeditationActivity.id.in_(created_ids))
    )
    await db_session.execute(delete(Activity).where(Activity.id.in_(created_ids)))
    await db_session.commit()


def _create_payload(**overrides: Any) -> MeditationCreate:
    defaults = {
        "name": "Respiração consciente",
        "description": "Uma meditação guiada de 5 minutos.",
        "audio_url": "https://example.com/meditacao.mp3",
        "max_duration_seconds": 300,
    }
    defaults.update(overrides)
    return MeditationCreate(**defaults)


# --- schemas -----------------------------------------------------------------


def test_meditation_create_defaults_to_enabled() -> None:
    payload = _create_payload()

    assert payload.enabled is True


def test_meditation_create_trims_whitespace() -> None:
    payload = _create_payload(name="  Respiração  ", description="  Descrição  ")

    assert payload.name == "Respiração"
    assert payload.description == "Descrição"


@pytest.mark.parametrize("field", ["name", "description", "audio_url"])
def test_meditation_create_rejects_blank_required_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        _create_payload(**{field: "   "})


def test_meditation_create_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        _create_payload(unknown_field="x")


@pytest.mark.parametrize(
    "field", ["name", "description", "audio_url", "max_duration_seconds", "enabled"]
)
def test_meditation_update_rejects_explicit_null(field: str) -> None:
    with pytest.raises(ValidationError):
        MeditationUpdate.model_validate({field: None})


@pytest.mark.parametrize("field, limit", [("name", 80), ("description", 300)])
def test_meditation_schemas_enforce_text_limits(field: str, limit: int) -> None:
    value = "x" * limit
    _create_payload(**{field: value})
    MeditationUpdate.model_validate({field: value})

    with pytest.raises(ValidationError):
        _create_payload(**{field: value + "x"})
    with pytest.raises(ValidationError):
        MeditationUpdate.model_validate({field: value + "x"})


def test_meditation_create_requires_duration() -> None:
    with pytest.raises(ValidationError, match="max_duration_seconds"):
        MeditationCreate.model_validate(
            {"name": "Respiração", "description": "Descrição", "audio_url": "meditacao.mp3"}
        )


@pytest.mark.parametrize("duration", [0, -1])
def test_meditation_schemas_reject_nonpositive_duration(duration: int) -> None:
    with pytest.raises(ValidationError, match="max_duration_seconds"):
        _create_payload(max_duration_seconds=duration)
    with pytest.raises(ValidationError, match="max_duration_seconds"):
        MeditationUpdate(max_duration_seconds=duration)


def test_meditation_update_allows_absent_fields() -> None:
    update = MeditationUpdate()

    assert update.model_fields_set == set()


# --- service -------------------------------------------------------------------


async def test_create_persists_meditation(create_meditation: CreateMeditation) -> None:
    meditation = await create_meditation()

    assert meditation.id is not None
    assert meditation.description == "Uma meditação guiada de 5 minutos."
    assert meditation.enabled is True
    assert meditation.deleted_at is None


async def test_list_enabled_excludes_disabled_and_deleted(
    db_session: AsyncSession, create_meditation: CreateMeditation
) -> None:
    service = MeditationService(db_session)

    visible = await create_meditation(name="Visível")
    disabled = await create_meditation(name="Desativada", enabled=False)
    deleted = await create_meditation(name="Excluída")
    await service.delete(deleted.id)

    result = await service.list_enabled()
    result_ids = {m.id for m in result}

    assert visible.id in result_ids
    assert disabled.id not in result_ids
    assert deleted.id not in result_ids


async def test_list_for_admin_filters_by_search_and_enabled(
    db_session: AsyncSession, create_meditation: CreateMeditation
) -> None:
    service = MeditationService(db_session)

    morning = await create_meditation(name="Meditação da manhã (teste busca)")
    night = await create_meditation(name="Meditação da noite (teste busca)", enabled=False)
    await create_meditation(
        name="Alongamento (teste busca)", description="Um exercício para o corpo."
    )

    items, total = await service.list_for_admin(page=1, page_size=10, search="meditação da")

    assert total == 2
    assert {m.id for m in items} == {morning.id, night.id}

    items, total = await service.list_for_admin(
        page=1, page_size=10, search="meditação da", enabled=True
    )

    assert total == 1
    assert items[0].id == morning.id


async def test_list_for_admin_excludes_deleted_but_keeps_disabled(
    db_session: AsyncSession, create_meditation: CreateMeditation
) -> None:
    service = MeditationService(db_session)

    disabled = await create_meditation(name="Desativada (teste exclusão)", enabled=False)
    deleted = await create_meditation(name="Excluída (teste exclusão)")
    await service.delete(deleted.id)

    items, _total = await service.list_for_admin(page=1, page_size=50, search="(teste exclusão)")
    item_ids = {m.id for m in items}

    assert item_ids == {disabled.id}


async def test_list_for_admin_paginates(
    db_session: AsyncSession, create_meditation: CreateMeditation
) -> None:
    service = MeditationService(db_session)

    for i in range(3):
        await create_meditation(name=f"Meditação paginação {i}")

    items, total = await service.list_for_admin(page=1, page_size=2, search="paginação")

    assert total == 3
    assert len(items) == 2


async def test_get_by_id_returns_disabled_item(
    db_session: AsyncSession, create_meditation: CreateMeditation
) -> None:
    service = MeditationService(db_session)
    meditation = await create_meditation(enabled=False)

    found = await service.get_by_id(meditation.id)

    assert found.id == meditation.id


async def test_get_by_id_raises_404_when_deleted(
    db_session: AsyncSession, create_meditation: CreateMeditation
) -> None:
    service = MeditationService(db_session)
    meditation = await create_meditation()
    await service.delete(meditation.id)

    with pytest.raises(Exception) as exc_info:
        await service.get_by_id(meditation.id)

    assert exc_info.value.status_code == 404


async def test_get_by_id_raises_404_when_not_found(db_session: AsyncSession) -> None:
    service = MeditationService(db_session)

    with pytest.raises(Exception) as exc_info:
        await service.get_by_id(uuid.uuid4())

    assert exc_info.value.status_code == 404


async def test_get_enabled_raises_404_when_disabled(
    db_session: AsyncSession, create_meditation: CreateMeditation
) -> None:
    service = MeditationService(db_session)
    meditation = await create_meditation(enabled=False)

    with pytest.raises(Exception) as exc_info:
        await service.get_enabled(meditation.id)

    assert exc_info.value.status_code == 404


async def test_update_changes_only_sent_fields(
    db_session: AsyncSession, create_meditation: CreateMeditation
) -> None:
    service = MeditationService(db_session)
    meditation = await create_meditation()

    updated = await service.update(meditation.id, MeditationUpdate(name="Novo nome"))

    assert updated.name == "Novo nome"
    assert updated.description == "Uma meditação guiada de 5 minutos."
    assert updated.audio_url == "https://example.com/meditacao.mp3"
    assert updated.max_duration_seconds == 300


async def test_update_can_reenable_disabled_meditation(
    db_session: AsyncSession, create_meditation: CreateMeditation
) -> None:
    service = MeditationService(db_session)
    meditation = await create_meditation(enabled=False)

    updated = await service.update(meditation.id, MeditationUpdate(enabled=True))

    assert updated.enabled is True


async def test_delete_is_a_logical_delete(
    db_session: AsyncSession, create_meditation: CreateMeditation
) -> None:
    service = MeditationService(db_session)
    meditation = await create_meditation()

    await service.delete(meditation.id)

    assert meditation.enabled is False
    assert meditation.deleted_at is not None
