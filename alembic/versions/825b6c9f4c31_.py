"""empty message

Revision ID: 825b6c9f4c31
Revises: f3a3f411b055
Create Date: 2026-09-10 22:31:49.020364

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "825b6c9f4c31"
down_revision: str | None = "f3a3f411b055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    activity_type = sa.Enum("BREATH", "MEDITATION", "SELF_REGULATION", name="activity_type")
    activity_type.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "activity",
        sa.Column(
            "type",
            sa.Enum(
                "BREATH", "MEDITATION", "SELF_REGULATION", name="activity_type", create_type=False
            ),
            nullable=False,
        ),
    )
    op.add_column(
        "activity_session",
        sa.Column(
            "type",
            sa.Enum(
                "BREATH", "MEDITATION", "SELF_REGULATION", name="activity_type", create_type=False
            ),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("activity_session", "type")
    op.drop_column("activity", "type")
    sa.Enum(name="activity_type").drop(op.get_bind(), checkfirst=True)
