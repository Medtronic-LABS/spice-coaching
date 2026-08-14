"""Rename module lifecycle timestamps; drop first_activated_at.

Revision ID: 0077
Revises: 0076
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0077"
down_revision: str | None = "0076"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("module", "last_reactivated_at", new_column_name="activated_at")
    op.alter_column("module", "last_deactivated_at", new_column_name="deactivated_at")
    op.execute(
        sa.text(
            """
            UPDATE module
            SET activated_at = COALESCE(activated_at, first_activated_at, published_at)
            WHERE activated_at IS NULL
              AND (first_activated_at IS NOT NULL OR published_at IS NOT NULL)
            """
        )
    )
    op.drop_column("module", "first_activated_at")


def downgrade() -> None:
    op.add_column(
        "module",
        sa.Column("first_activated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE module
            SET first_activated_at = activated_at
            WHERE activated_at IS NOT NULL
            """
        )
    )
    op.alter_column("module", "activated_at", new_column_name="last_reactivated_at")
    op.alter_column("module", "deactivated_at", new_column_name="last_deactivated_at")
