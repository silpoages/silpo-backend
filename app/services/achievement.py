import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import distinct, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.achievement_catalog import (
    ACHIEVEMENT_CATALOG,
    ACHIEVEMENTS_BY_ID,
    CATALOG_ACHIEVEMENT_IDS,
)
from app.enums import AchievementRule, ActivityType
from app.models.achievement import Achievement
from app.models.achievement_log import AchievementLog
from app.models.activity_session import ActivitySession
from app.models.diary_entry import DiaryEntry
from app.models.good_practice_log import GoodPracticeLog
from app.models.mood_log import MoodLog
from app.models.user import User
from app.schemas.achievement import AchievementProgress, AchievementRead

logger = logging.getLogger(__name__)


def available_achievement_filter() -> tuple[ColumnElement[bool], ...]:
    """Conquistas que o usuário pode ver e desbloquear: as do catálogo, habilitadas.

    Compartilhado com a Jornada, para os totais das duas APIs nunca divergirem.
    """
    return (
        Achievement.id.in_(CATALOG_ACHIEVEMENT_IDS),
        Achievement.enabled.is_(True),
        Achievement.deleted_at.is_(None),
    )


class AchievementService:
    """Calcula o progresso das conquistas a partir dos dados salvos e registra os desbloqueios."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_progress(self, user_id: uuid.UUID) -> dict[AchievementRule, int]:
        """Contagem de cada regra do catálogo para o usuário, em uma única ida ao banco.

        Só são salvos registros de ações concluídas (uma sessão de exercício só é gravada ao
        terminar), então todos contam. Do Diário só se conta o id: texto e imagem não são lidos.
        """
        counts = {
            AchievementRule.MOOD_LOGS: select(func.count(MoodLog.id)).where(
                MoodLog.user_id == user_id
            ),
            # Mesma referência de data da Jornada: `log_date`, gravado em UTC.
            AchievementRule.MOOD_DAYS: select(func.count(distinct(MoodLog.log_date))).where(
                MoodLog.user_id == user_id
            ),
            AchievementRule.DISTINCT_MOODS: select(func.count(distinct(MoodLog.mood))).where(
                MoodLog.user_id == user_id
            ),
            AchievementRule.GOOD_PRACTICE_LOGS: select(func.count(GoodPracticeLog.id)).where(
                GoodPracticeLog.user_id == user_id
            ),
            AchievementRule.DISTINCT_GOOD_PRACTICES: select(
                func.count(distinct(GoodPracticeLog.good_practice_id))
            ).where(GoodPracticeLog.user_id == user_id),
            AchievementRule.BREATHING_SESSIONS: select(func.count(ActivitySession.id)).where(
                ActivitySession.user_id == user_id,
                ActivitySession.type == ActivityType.BREATHING,
            ),
            # Práticas do Bem ficam em GoodPracticeLog, então não entram aqui.
            AchievementRule.EXERCISE_SESSIONS: select(func.count(ActivitySession.id)).where(
                ActivitySession.user_id == user_id
            ),
            AchievementRule.DIARY_ENTRIES: select(func.count(DiaryEntry.id)).where(
                DiaryEntry.user_id == user_id,
                DiaryEntry.enabled.is_(True),
                DiaryEntry.deleted_at.is_(None),
            ),
        }
        result = await self.db.execute(
            select(*(query.scalar_subquery().label(rule.value) for rule, query in counts.items()))
        )
        row = result.one()
        return {rule: getattr(row, rule.value) for rule in counts}

    async def evaluate(self, user_id: uuid.UUID, *, acknowledged: bool = False) -> list[uuid.UUID]:
        """Registra as conquistas cujas metas o usuário já atingiu e devolve as recém-desbloqueadas.

        Idempotente e segura a concorrência: a constraint única de (usuário, conquista) com
        `ON CONFLICT DO NOTHING` impede duplicidade. Desbloqueios nunca são removidos, mesmo
        que um registro antigo seja excluído depois. Com `acknowledged=True` (avaliação
        retroativa), o desbloqueio já nasce visto e não gera alerta.
        """
        unlocked = await self._unlock_reached(user_id, acknowledged=acknowledged)
        await self.db.commit()
        return unlocked

    async def evaluate_after_action(self, user_id: uuid.UUID) -> None:
        """Avalia depois que a ação principal já foi salva, sem nunca fazê-la falhar.

        O savepoint isola uma falha da avaliação: ela é desfeita sozinha, sem expirar nem
        desfazer o registro que acabou de ser salvo.
        """
        try:
            async with self.db.begin_nested():
                await self._unlock_reached(user_id, acknowledged=False)
            await self.db.commit()
        except Exception:
            logger.exception("Failed to evaluate achievements for user %s", user_id)

    async def list_for_user(self, user_id: uuid.UUID) -> list[AchievementRead]:
        """Todas as conquistas disponíveis, com o progresso e o desbloqueio do usuário.

        Se uma meta já foi atingida mas o desbloqueio não foi registrado (por exemplo, numa
        falha da avaliação pós-ação), ele é registrado aqui já como visto: a lista fica coerente
        com o progresso sem disparar alerta de algo que o usuário não acabou de fazer.
        """
        achievements = await self._available_achievements()
        if not achievements:
            return []
        progress = await self.get_progress(user_id)
        await self._insert_unlocks(
            user_id, self._reached_ids(achievements, progress), acknowledged=True
        )
        await self.db.commit()

        unlocks = await self._unlocks_by_achievement(user_id)
        items = []
        for achievement in achievements:
            definition = ACHIEVEMENTS_BY_ID[achievement.id]
            log = unlocks.get(achievement.id)
            items.append(
                AchievementRead(
                    id=achievement.id,
                    name=achievement.name,
                    description=achievement.description,
                    icon=achievement.image_url,
                    category=definition.category,
                    unlocked=log is not None,
                    progress=AchievementProgress(
                        current=min(progress[definition.rule], definition.target),
                        target=definition.target,
                    ),
                    unlocked_at=log.achieved_at if log else None,
                )
            )
        return items

    async def list_pending(self, user_id: uuid.UUID) -> list[AchievementRead]:
        """Desbloqueios cujo alerta o usuário ainda não confirmou, do mais antigo ao mais novo."""
        items = [item for item in await self.list_for_user(user_id) if item.unlocked]
        pending_ids = set(
            await self.db.scalars(
                select(AchievementLog.achievement_id).where(
                    AchievementLog.user_id == user_id, AchievementLog.acknowledged_at.is_(None)
                )
            )
        )
        pending = [item for item in items if item.id in pending_ids]
        return sorted(
            pending,
            key=lambda item: (item.unlocked_at or datetime.min.replace(tzinfo=UTC), item.name),
        )

    async def acknowledge(self, user_id: uuid.UUID, achievement_id: uuid.UUID) -> bool:
        """Confirma que o usuário viu o alerta. Repetir não muda nada.

        Devolve `False` se a conquista não está disponível ou não foi desbloqueada por ele.
        """
        log_id = await self.db.scalar(
            select(AchievementLog.id)
            .join(Achievement, Achievement.id == AchievementLog.achievement_id)
            .where(
                AchievementLog.user_id == user_id,
                AchievementLog.achievement_id == achievement_id,
                *available_achievement_filter(),
            )
        )
        if log_id is None:
            return False

        await self.db.execute(
            update(AchievementLog)
            .where(AchievementLog.id == log_id, AchievementLog.acknowledged_at.is_(None))
            .values(acknowledged_at=datetime.now(UTC))
        )
        await self.db.commit()
        return True

    async def _unlock_reached(self, user_id: uuid.UUID, *, acknowledged: bool) -> list[uuid.UUID]:
        achievements = await self._available_achievements()
        if not achievements:
            return []
        progress = await self.get_progress(user_id)
        return await self._insert_unlocks(
            user_id, self._reached_ids(achievements, progress), acknowledged=acknowledged
        )

    async def _available_achievements(self) -> list[Achievement]:
        rows = {
            row.id: row
            for row in await self.db.scalars(
                select(Achievement).where(*available_achievement_filter())
            )
        }
        # Na ordem do catálogo, para a lista ser estável.
        return [rows[definition.id] for definition in ACHIEVEMENT_CATALOG if definition.id in rows]

    @staticmethod
    def _reached_ids(
        achievements: list[Achievement], progress: dict[AchievementRule, int]
    ) -> list[uuid.UUID]:
        return [
            achievement.id
            for achievement in achievements
            if progress[ACHIEVEMENTS_BY_ID[achievement.id].rule]
            >= ACHIEVEMENTS_BY_ID[achievement.id].target
        ]

    async def _insert_unlocks(
        self, user_id: uuid.UUID, achievement_ids: list[uuid.UUID], *, acknowledged: bool
    ) -> list[uuid.UUID]:
        if not achievement_ids:
            return []
        now = datetime.now(UTC)
        statement = (
            insert(AchievementLog)
            .values(
                [
                    {
                        "id": uuid.uuid4(),
                        "user_id": user_id,
                        "achievement_id": achievement_id,
                        "achieved_at": now,
                        "acknowledged_at": now if acknowledged else None,
                    }
                    for achievement_id in achievement_ids
                ]
            )
            .on_conflict_do_nothing(constraint="uq_achievement_log_user_achievement")
            .returning(AchievementLog.achievement_id)
        )
        return list(await self.db.scalars(statement))

    async def _unlocks_by_achievement(self, user_id: uuid.UUID) -> dict[uuid.UUID, AchievementLog]:
        logs = await self.db.scalars(
            select(AchievementLog).where(AchievementLog.user_id == user_id)
        )
        return {log.achievement_id: log for log in logs}

    async def backfill(self) -> int:
        """Avalia retroativamente todos os usuários ativos, sem gerar alertas históricos.

        Devolve quantos desbloqueios foram registrados.
        """
        user_ids = list(await self.db.scalars(select(User.id).where(User.deleted_at.is_(None))))
        total = 0
        for user_id in user_ids:
            total += len(await self.evaluate(user_id, acknowledged=True))
        return total
