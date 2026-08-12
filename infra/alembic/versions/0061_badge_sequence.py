"""Add nullable sequence to badge for display order.

Revision ID: 0061
Revises: 0060
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0061"
down_revision: str | None = "0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("badge", sa.Column("sequence", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("badge", "sequence")
