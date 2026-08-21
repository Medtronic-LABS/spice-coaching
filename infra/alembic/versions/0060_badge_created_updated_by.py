"""Add created_by and updated_by to badge.

Revision ID: 0060
Revises: 0059
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0060"
down_revision: str | None = "0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("badge", sa.Column("created_by", sa.Text(), nullable=True))
    op.add_column("badge", sa.Column("updated_by", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("badge", "updated_by")
    op.drop_column("badge", "created_by")
