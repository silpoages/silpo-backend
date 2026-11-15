"""Avaliação retroativa das conquistas para usuários que já tinham registros.

Os desbloqueios encontrados aqui já nascem vistos (`acknowledged_at` preenchido), para o app
não mostrar de uma vez alertas de conquistas antigas. Pode ser executado mais de uma vez.

Uso: uv run python -m scripts.backfill_achievements
"""

import asyncio

from app.db.session import async_session_maker
from app.services.achievement import AchievementService


async def backfill_achievements() -> None:
    async with async_session_maker() as db:
        unlocked = await AchievementService(db).backfill()
    print(f"\n✅ Avaliação retroativa concluída: {unlocked} desbloqueio(s) registrado(s).\n")


if __name__ == "__main__":
    asyncio.run(backfill_achievements())
