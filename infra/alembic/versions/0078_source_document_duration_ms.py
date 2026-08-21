"""Add source_document.duration_ms for audio/video length.

Revision ID: 0078
Revises: 0077
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0078"
down_revision: str | None = "0077"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("source_document", sa.Column("duration_ms", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("source_document", "duration_ms")
