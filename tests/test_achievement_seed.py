import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.achievement_catalog import ACHIEVEMENT_CATALOG, ACHIEVEMENTS_BY_CODE
from app.enums import AchievementCategory, AchievementRule
from app.models.achievement import Achievement
from app.models.achievement_log import AchievementLog
from app.models.user import User
from scripts.seed import LEGACY_SAMPLE_ACHIEVEMENT, ensure_default_achievements

CATALOG_IDS = [definition.id for definition in ACHIEVEMENT_CATALOG]

# O banco é compartilhado entre testes: nada aqui é commitado, então cada teste
# enxerga as próprias alterações e a sessão as descarta ao final.


async def _catalog_rows(db_session: AsyncSession) -> list[Achievement]:
    result = await db_session.scalars(select(Achievement).where(Achievement.id.in_(CATALOG_IDS)))
    return list(result.all())


def test_catalog_has_the_ten_initial_achievements() -> None:
    expected = {
        "Primeiro passo": (AchievementRule.MOOD_LOGS, 1),
        "Me conhecendo melhor": (AchievementRule.MOOD_DAYS, 7),
        "Todas as emoções importam": (AchievementRule.DISTINCT_MOODS, 3),
        "Pequenas vitórias": (AchievementRule.GOOD_PRACTICE_LOGS, 1),
        "Cultivando o bem": (AchievementRule.GOOD_PRACTICE_LOGS, 5),
        "Explorando possibilidades": (AchievementRule.DISTINCT_GOOD_PRACTICES, 3),
        "Um momento para respirar": (AchievementRule.BREATHING_SESSIONS, 1),
        "Cuidando de mim": (AchievementRule.EXERCISE_SESSIONS, 10),
        "Minha história importa": (AchievementRule.DIARY_ENTRIES, 1),
        "Colocando em palavras": (AchievementRule.DIARY_ENTRIES, 5),
    }

    assert {d.name: (d.rule, d.target) for d in ACHIEVEMENT_CATALOG} == expected
    assert len({d.id for d in ACHIEVEMENT_CATALOG}) == len(expected)
    assert len(ACHIEVEMENTS_BY_CODE) == len(expected)
    for definition in ACHIEVEMENT_CATALOG:
        assert definition.description
        assert definition.icon
        assert isinstance(definition.category, AchievementCategory)


async def test_seed_creates_catalog_achievements_enabled(db_session: AsyncSession) -> None:
    await ensure_default_achievements(db_session)

    rows = {row.id: row for row in await _catalog_rows(db_session)}
    assert set(rows) == set(CATALOG_IDS)
    for definition in ACHIEVEMENT_CATALOG:
        row = rows[definition.id]
        assert row.name == definition.name
        assert row.description == definition.description
        assert row.image_url == definition.icon
        assert row.enabled is True
        assert row.deleted_at is None


async def test_seed_is_idempotent(db_session: AsyncSession) -> None:
    for _ in range(3):
        await ensure_default_achievements(db_session)

    total = await db_session.scalar(
        select(func.count(Achievement.id)).where(Achievement.id.in_(CATALOG_IDS))
    )
    assert total == len(ACHIEVEMENT_CATALOG)
    for definition in ACHIEVEMENT_CATALOG:
        same_name = await db_session.scalar(
            select(func.count(Achievement.id)).where(
                Achievement.name == definition.name, Achievement.image_url == definition.icon
            )
        )
        assert same_name == 1


async def test_seed_does_not_overwrite_existing_records(db_session: AsyncSession) -> None:
    await ensure_default_achievements(db_session)
    first_step = await db_session.get(Achievement, ACHIEVEMENTS_BY_CODE["first_step"].id)
    assert first_step is not None
    first_step.description = "Descrição editada"
    first_step.enabled = False

    unrelated = Achievement(
        id=uuid.uuid4(), name="Outra conquista", description="x", image_url="star-outline"
    )
    db_session.add(unrelated)
    await db_session.flush()

    await ensure_default_achievements(db_session)

    await db_session.refresh(first_step)
    await db_session.refresh(unrelated)
    assert first_step.description == "Descrição editada"
    assert first_step.enabled is False
    assert unrelated.name == "Outra conquista"
    assert unrelated.enabled is True


async def test_seed_disables_legacy_sample_achievement_keeping_logs(
    db_session: AsyncSession, create_user: Callable[..., Awaitable[User]]
) -> None:
    user = await create_user()
    legacy_name, legacy_description = LEGACY_SAMPLE_ACHIEVEMENT
    legacy = Achievement(
        id=uuid.uuid4(),
        name=legacy_name,
        description=legacy_description,
        image_url="https://example.com/legacy.png",
    )
    db_session.add(legacy)
    await db_session.flush()
    log = AchievementLog(user_id=user.id, achievement_id=legacy.id)
    db_session.add(log)
    await db_session.flush()

    await ensure_default_achievements(db_session)

    await db_session.refresh(legacy)
    assert legacy.enabled is False
    assert await db_session.get(AchievementLog, log.id) is not None
