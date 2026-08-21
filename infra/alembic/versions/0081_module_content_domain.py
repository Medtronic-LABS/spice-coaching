"""Add nullable content_domain to module.

Revision ID: 0081
Revises: 0080
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0081"
down_revision: str | None = "0080"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("module", sa.Column("content_domain", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("module", "content_domain")
