"""merge heads

Revision ID: 03a66faf7d7c
Revises: 825b6c9f4c31, 8317b5864c76
Create Date: 2026-09-12 13:11:59.379964

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "03a66faf7d7c"
down_revision: str | None = ("825b6c9f4c31", "8317b5864c76")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
