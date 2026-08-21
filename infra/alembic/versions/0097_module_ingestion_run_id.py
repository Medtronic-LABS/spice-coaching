"""Add nullable module.ingestion_run_id for latest-run module filtering.

Revision ID: 0097
Revises: 0096
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0097"
down_revision: str | None = "0096"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "module",
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_module_ingestion_run_id",
        "module",
        "ingestion_run",
        ["ingestion_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_module_ingestion_run_id", "module", ["ingestion_run_id"])


def downgrade() -> None:
    op.drop_index("ix_module_ingestion_run_id", table_name="module")
    op.drop_constraint("fk_module_ingestion_run_id", "module", type_="foreignkey")
    op.drop_column("module", "ingestion_run_id")
