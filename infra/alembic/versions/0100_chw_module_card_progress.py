"""CHW module card progress — per-card view tracking.

Revision ID: 0100
Revises: 0099
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0100"
down_revision: str | None = "0099"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chw_module_card_progress",
        sa.Column("chw_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "module_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("module.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "card_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("module_card.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "first_viewed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint(
            "chw_id",
            "module_id",
            "card_id",
            name="pk_chw_module_card_progress",
        ),
    )
    op.create_index(
        "ix_chw_module_card_progress_chw_module",
        "chw_module_card_progress",
        ["chw_id", "module_id"],
        unique=False,
    )
    op.create_index(
        "ix_chw_module_card_progress_tenant_id",
        "chw_module_card_progress",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chw_module_card_progress_tenant_id", table_name="chw_module_card_progress")
    op.drop_index("ix_chw_module_card_progress_chw_module", table_name="chw_module_card_progress")
    op.drop_table("chw_module_card_progress")
