"""add unique user/achievement and acknowledged_at to achievement_log

Revision ID: 4b7e9d2c1a6f
Revises: fa7c59947e7c
Create Date: 2026-11-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b7e9d2c1a6f"
down_revision: str | None = "fa7c59947e7c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Duplicatas anteriores à constraint: fica o desbloqueio mais antigo de cada par.
    op.execute(
        """
        DELETE FROM achievement_log AS duplicate
        USING achievement_log AS kept
        WHERE duplicate.user_id = kept.user_id
          AND duplicate.achievement_id = kept.achievement_id
          AND (duplicate.achieved_at, duplicate.id) > (kept.achieved_at, kept.id)
        """
    )
    op.create_unique_constraint(
        "uq_achievement_log_user_achievement", "achievement_log", ["user_id", "achievement_id"]
    )

    op.add_column(
        "achievement_log",
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Desbloqueios já existentes contam como vistos, para não virarem alertas em massa.
    op.execute("UPDATE achievement_log SET acknowledged_at = achieved_at")


def downgrade() -> None:
    op.drop_column("achievement_log", "acknowledged_at")
    op.drop_constraint("uq_achievement_log_user_achievement", "achievement_log", type_="unique")
