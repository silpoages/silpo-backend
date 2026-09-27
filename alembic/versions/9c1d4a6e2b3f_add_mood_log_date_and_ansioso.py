"""add mood_log.log_date unique constraint and ANSIOSO mood value

Revision ID: 9c1d4a6e2b3f
Revises: 387f2be3849c
Create Date: 2026-09-27 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c1d4a6e2b3f"
down_revision: str | None = "387f2be3849c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE mood ADD VALUE IF NOT EXISTS 'ANSIOSO'")

    op.add_column("mood_log", sa.Column("log_date", sa.Date(), nullable=True))
    op.execute("UPDATE mood_log SET log_date = (posted_at AT TIME ZONE 'UTC')::date")
    op.alter_column("mood_log", "log_date", nullable=False)
    op.create_unique_constraint("uq_mood_log_user_date", "mood_log", ["user_id", "log_date"])


def downgrade() -> None:
    op.drop_constraint("uq_mood_log_user_date", "mood_log", type_="unique")
    op.drop_column("mood_log", "log_date")

    # Postgres não suporta remover um valor de enum diretamente — recria o tipo sem
    # 'ANSIOSO'. Falha se alguma linha existente usar esse valor (esperado: downgrade
    # de um valor em uso não é suportado).
    op.execute("ALTER TYPE mood RENAME TO mood_old")
    op.execute("CREATE TYPE mood AS ENUM ('FELIZ', 'BEM', 'CANSADO', 'TRISTE', 'IRRITADO')")
    op.execute("ALTER TABLE mood_log ALTER COLUMN mood TYPE mood USING mood::text::mood")
    op.execute("DROP TYPE mood_old")
