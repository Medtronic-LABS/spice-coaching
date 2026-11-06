"""Add assign_to_all to module and source_document.

Revision ID: 0106
Revises: 0105
Create Date: 2026-11-05

Existing rows are backfilled to false (server default) so current production
behaviour is preserved; the ORM default of true applies only to new rows.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0106"
down_revision: str | None = "0105"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("module", "source_document")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("assign_to_all", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_column(table, "assign_to_all")
