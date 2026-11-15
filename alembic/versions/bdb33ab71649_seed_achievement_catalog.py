"""seed achievement catalog

Revision ID: bdb33ab71649
Revises: 4b7e9d2c1a6f
Create Date: 2026-11-15 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bdb33ab71649"
down_revision: str | None = "4b7e9d2c1a6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Cópia do `app/core/achievement_catalog.py` neste momento (id, nome, descrição, ícone). Fica
# congelada aqui de propósito: a migração não pode mudar de comportamento se o catálogo mudar
# depois — conquistas novas entram por uma migração nova.
CATALOG: tuple[tuple[str, str, str, str], ...] = (
    (
        "f19be169-97bb-57be-ae34-8cbfa6760a41",
        "Primeiro passo",
        "Registre como você está se sentindo pela primeira vez",
        "leaf-outline",
    ),
    (
        "81ac122a-ea35-51c5-b31d-f20e89bd713a",
        "Me conhecendo melhor",
        "Registre emoções em 7 dias diferentes",
        "calendar-outline",
    ),
    (
        "70510413-026a-50d3-b8f5-fdf885ea710d",
        "Todas as emoções importam",
        "Registre 3 emoções diferentes",
        "color-palette-outline",
    ),
    (
        "07f93791-7e4b-5ad1-b494-a254b2924614",
        "Pequenas vitórias",
        "Conclua sua primeira prática do bem",
        "sparkles-outline",
    ),
    (
        "f9297ae3-e9bd-577c-838e-b274fc60096f",
        "Cultivando o bem",
        "Conclua 5 práticas do bem",
        "flower-outline",
    ),
    (
        "462dfc64-14ac-5915-a15e-0e5198d97457",
        "Explorando possibilidades",
        "Conclua 3 práticas do bem diferentes",
        "compass-outline",
    ),
    (
        "bb0bfde9-9337-5943-ab52-2eab7334d928",
        "Um momento para respirar",
        "Conclua sua primeira sessão de respiração",
        "water-outline",
    ),
    (
        "047a074e-ac2e-5ee8-b4bc-c947178df19b",
        "Cuidando de mim",
        "Conclua 10 sessões de exercícios",
        "heart-outline",
    ),
    (
        "6f2895f0-ce8a-57f0-b548-ad1ef07c5124",
        "Minha história importa",
        "Faça seu primeiro registro no diário",
        "book-outline",
    ),
    (
        "6b518329-ac38-5820-84c9-334ddacc622c",
        "Colocando em palavras",
        "Faça 5 registros no diário",
        "create-outline",
    ),
)

# Conquista de exemplo das versões antigas do seed (id aleatório): sai da contagem, os logs ficam.
LEGACY_NAME = "Primeiro Passo"
LEGACY_DESCRIPTION = "Completou a primeira atividade no Silpo."

achievement = sa.table(
    "achievement",
    sa.column("id", postgresql.UUID(as_uuid=False)),
    sa.column("name", sa.Text),
    sa.column("description", sa.Text),
    sa.column("image_url", sa.Text),
    sa.column("enabled", sa.Boolean),
)


def upgrade() -> None:
    # Não sobrescreve nada: bancos onde o seed já rodou mantêm os próprios registros.
    op.execute(
        postgresql.insert(achievement)
        .values(
            [
                {"id": id_, "name": name, "description": description, "image_url": icon}
                for id_, name, description, icon in CATALOG
            ]
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    op.execute(
        achievement.update()
        .where(
            achievement.c.name == LEGACY_NAME,
            achievement.c.description == LEGACY_DESCRIPTION,
            achievement.c.enabled.is_(True),
        )
        .values(enabled=False)
    )


def downgrade() -> None:
    # Só remove conquistas que ninguém desbloqueou; as com histórico ficam.
    op.execute(
        sa.text(
            """
            DELETE FROM achievement
            WHERE id = ANY(CAST(:ids AS uuid[]))
              AND NOT EXISTS (
                SELECT 1 FROM achievement_log WHERE achievement_log.achievement_id = achievement.id
              )
            """
        ).bindparams(ids=[id_ for id_, *_ in CATALOG])
    )
