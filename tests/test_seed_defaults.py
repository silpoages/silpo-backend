import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import scripts.seed as seed_module
from app.core.achievement_catalog import ACHIEVEMENT_CATALOG
from app.models import Achievement, BreathingActivity, GoodPractice, SelfRegulationActivity, User
from scripts.seed import ensure_defaults

RunSeed = Callable[..., Awaitable[None]]

SEED_EMAILS = (
    "email@email.com",
    "teixeira.gabriela@google.com",
    "sol.andrade@terra.com",
    "rafael.tavares@uol.com",
)


@pytest.fixture
def run_seed(monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession) -> RunSeed:
    """Roda `seed()` na sessão do teste, sem gravar nada (commit vira flush)."""

    @asynccontextmanager
    async def session_maker() -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setattr(seed_module, "async_session_maker", session_maker)
    monkeypatch.setattr(db_session, "commit", db_session.flush)

    async def _run(*args: str) -> None:
        monkeypatch.setattr(sys, "argv", ["seed", *args])
        await seed_module.seed()

    return _run


async def _count(db_session: AsyncSession, model: type, *where: object) -> int:
    return int(await db_session.scalar(select(func.count()).select_from(model).where(*where)) or 0)


async def test_defaults_only_creates_reference_data_and_no_users(
    db_session: AsyncSession, run_seed: RunSeed
) -> None:
    users_before = await _count(db_session, User)

    await run_seed("--defaults-only")

    assert await _count(db_session, User) == users_before
    assert await _count(db_session, User, User.email.in_(SEED_EMAILS)) == 0
    assert await _count(db_session, BreathingActivity, BreathingActivity.name == "Respiração 4-7-8")
    assert await _count(
        db_session, SelfRegulationActivity, SelfRegulationActivity.name == "Estoura Bolhas"
    )
    assert await _count(db_session, GoodPractice) >= 8
    assert await _count(
        db_session, Achievement, Achievement.id.in_([d.id for d in ACHIEVEMENT_CATALOG])
    ) == len(ACHIEVEMENT_CATALOG)


async def test_defaults_only_is_idempotent(db_session: AsyncSession, run_seed: RunSeed) -> None:
    await run_seed("--defaults-only")
    practices = await _count(db_session, GoodPractice)
    activities = await _count(db_session, BreathingActivity) + await _count(
        db_session, SelfRegulationActivity
    )

    await run_seed("--defaults-only")
    await run_seed("--defaults-only")

    assert await _count(db_session, GoodPractice) == practices
    assert (
        await _count(db_session, BreathingActivity)
        + await _count(db_session, SelfRegulationActivity)
        == activities
    )


async def test_defaults_do_not_bring_back_what_the_admin_disabled_or_deleted(
    db_session: AsyncSession,
) -> None:
    await ensure_defaults(db_session)
    # O banco dos testes é compartilhado: desativa todas as linhas com esse nome, para que
    # nenhuma ativa sirva de "já existe" (com a regra antiga, o seed recriaria as duas).
    practices = list(
        await db_session.scalars(
            select(GoodPractice).where(GoodPractice.title == "Agradeça alguém")
        )
    )
    activities = list(
        await db_session.scalars(
            select(BreathingActivity).where(BreathingActivity.name == "Respiração 4-7-8")
        )
    )
    assert practices and activities
    for practice in practices:
        practice.enabled = False
    for activity in activities:
        activity.enabled = False
        activity.deleted_at = datetime.now(UTC)
    await db_session.flush()

    await ensure_defaults(db_session)

    assert await _count(db_session, GoodPractice, GoodPractice.title == "Agradeça alguém") == len(
        practices
    )
    assert await _count(
        db_session, BreathingActivity, BreathingActivity.name == "Respiração 4-7-8"
    ) == len(activities)
    assert (
        await _count(
            db_session,
            GoodPractice,
            GoodPractice.title == "Agradeça alguém",
            GoodPractice.enabled.is_(True),
        )
        == 0
    )


@pytest.mark.parametrize("destructive", ["--reset", "--clear-db"])
async def test_defaults_only_refuses_destructive_flags(
    monkeypatch: pytest.MonkeyPatch, run_seed: RunSeed, destructive: str
) -> None:
    async def fail_clear_db(_db: object) -> None:
        raise AssertionError("clear_db não pode rodar")

    monkeypatch.setattr(seed_module, "clear_db", fail_clear_db)

    with pytest.raises(SystemExit):
        await run_seed("--defaults-only", destructive)
