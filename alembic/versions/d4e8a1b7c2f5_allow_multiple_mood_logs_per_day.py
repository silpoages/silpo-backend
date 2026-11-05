"""allow multiple mood logs per user per day

Revision ID: d4e8a1b7c2f5
Revises: c7e2f4a9d1b3
Create Date: 2026-11-05 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e8a1b7c2f5"
down_revision: str | None = "c7e2f4a9d1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_mood_log_user_date", "mood_log", type_="unique")
    op.create_index("ix_mood_log_user_id_log_date", "mood_log", ["user_id", "log_date"])


def downgrade() -> None:
    op.drop_index("ix_mood_log_user_id_log_date", table_name="mood_log")
    op.create_unique_constraint("uq_mood_log_user_date", "mood_log", ["user_id", "log_date"])
