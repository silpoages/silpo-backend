"""Refactor Breathing Tables

Revision ID: ba3ad1b001d7
Revises: 387f2be3849c
Create Date: 2026-09-18 11:38:59.624587

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ba3ad1b001d7"
down_revision: str | None = "387f2be3849c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE activity_type RENAME VALUE 'BREATH' TO 'BREATHING'")
    op.rename_table("breath_activity", "breathing_activity")


def downgrade() -> None:
    op.rename_table("breathing_activity", "breath_activity")
    op.execute("ALTER TYPE activity_type RENAME VALUE 'BREATHING' TO 'BREATH'")
