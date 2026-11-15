import importlib.util
import uuid
from pathlib import Path
from types import ModuleType

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.achievement_catalog import ACHIEVEMENT_CATALOG
from app.models.achievement import Achievement

MIGRATION = Path("alembic/versions/bdb33ab71649_seed_achievement_catalog.py")


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_achievement_catalog", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_snapshot_matches_the_catalog() -> None:
    # Se o catálogo mudar, crie uma migração nova em vez de editar esta.
    snapshot = {
        uuid.UUID(id_): (name, description, icon)
        for id_, name, description, icon in _load_migration().CATALOG
    }

    assert snapshot == {d.id: (d.name, d.description, d.icon) for d in ACHIEVEMENT_CATALOG}


async def test_migrated_database_has_the_catalog_enabled(db_session: AsyncSession) -> None:
    # O banco dos testes é criado com `alembic upgrade head`, como o de produção.
    rows = {
        row.id: row
        for row in await db_session.scalars(
            select(Achievement).where(Achievement.id.in_([d.id for d in ACHIEVEMENT_CATALOG]))
        )
    }

    assert set(rows) == {d.id for d in ACHIEVEMENT_CATALOG}
    for definition in ACHIEVEMENT_CATALOG:
        row = rows[definition.id]
        assert (row.name, row.description, row.image_url) == (
            definition.name,
            definition.description,
            definition.icon,
        )
        assert row.enabled is True
        assert row.deleted_at is None
