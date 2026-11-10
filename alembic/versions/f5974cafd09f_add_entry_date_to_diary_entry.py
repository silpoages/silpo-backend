"""add entry_date to diary_entry

Revision ID: f5974cafd09f
Revises: d4e8a1b7c2f5
Create Date: 2026-11-05 18:39:50.500284

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f5974cafd09f"
down_revision: str | None = "d4e8a1b7c2f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("diary_entry", sa.Column("entry_date", sa.Date(), nullable=True))
    op.execute("UPDATE diary_entry SET entry_date = (created_at AT TIME ZONE 'UTC')::date")
    op.alter_column("diary_entry", "entry_date", existing_type=sa.Date(), nullable=False)
    op.alter_column("diary_entry", "mood_log_id", existing_type=sa.UUID(), nullable=True)
    op.create_index(
        "ix_diary_entry_user_id_entry_date",
        "diary_entry",
        ["user_id", "entry_date"],
        unique=False,
    )


def downgrade() -> None:
    orphans = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM diary_entry WHERE mood_log_id IS NULL"))
        .scalar_one()
    )
    if orphans:
        raise RuntimeError(
            f"Downgrade bloqueado: {orphans} relato(s) sem mood_log_id. "
            "Vincule ou remova esses relatos antes de reverter."
        )
    op.drop_index("ix_diary_entry_user_id_entry_date", table_name="diary_entry")
    op.alter_column("diary_entry", "mood_log_id", existing_type=sa.UUID(), nullable=False)
    op.drop_column("diary_entry", "entry_date")
