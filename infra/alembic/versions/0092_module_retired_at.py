"""Rename module.deprecated_at to retired_at.

Revision ID: 0092
Revises: 0091
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0092"
down_revision: str | None = "0091"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("module", "deprecated_at", new_column_name="retired_at")


def downgrade() -> None:
    op.alter_column("module", "retired_at", new_column_name="deprecated_at")
