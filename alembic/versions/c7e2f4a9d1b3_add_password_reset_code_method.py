"""add method and failed_attempts to password reset code

Revision ID: c7e2f4a9d1b3
Revises: a2b5578ba656
Create Date: 2026-10-27 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7e2f4a9d1b3"
down_revision: str | None = "a2b5578ba656"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    password_reset_method = sa.Enum("LINK", "CODE", name="password_reset_method")
    password_reset_method.create(op.get_bind(), checkfirst=True)

    # Existing rows were all created by the link flow.
    op.add_column(
        "password_reset_code",
        sa.Column(
            "method",
            sa.Enum("LINK", "CODE", name="password_reset_method", create_type=False),
            server_default="LINK",
            nullable=False,
        ),
    )
    op.add_column(
        "password_reset_code",
        sa.Column("failed_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("password_reset_code", "failed_attempts")
    op.drop_column("password_reset_code", "method")
    sa.Enum(name="password_reset_method").drop(op.get_bind(), checkfirst=True)
