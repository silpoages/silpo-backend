"""add description to meditation_activity

Revision ID: fa7c59947e7c
Revises: c7e2f4a9d1b3
Create Date: 2026-10-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fa7c59947e7c"
down_revision: str | None = "c7e2f4a9d1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing rows (seed data) didn't have a description; backfill with empty string
    # so admins can fill it in later without a migration failure on NOT NULL.
    op.add_column(
        "meditation_activity",
        sa.Column("description", sa.Text(), server_default="", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("meditation_activity", "description")
