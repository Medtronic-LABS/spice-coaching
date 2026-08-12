"""Add chw_badge earned-assignment table.

Revision ID: 0062
Revises: 0061
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0062"
down_revision: str | None = "0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chw_badge",
        sa.Column("chw_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "badge_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("badge.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "earned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("chw_id", "badge_id", name="pk_chw_badge"),
    )
    op.create_index("ix_chw_badge_chw_id", "chw_badge", ["chw_id"], unique=False)
    op.create_index("ix_chw_badge_badge_id", "chw_badge", ["badge_id"], unique=False)
    op.create_index("ix_chw_badge_tenant_id", "chw_badge", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chw_badge_tenant_id", table_name="chw_badge")
    op.drop_index("ix_chw_badge_badge_id", table_name="chw_badge")
    op.drop_index("ix_chw_badge_chw_id", table_name="chw_badge")
    op.drop_table("chw_badge")
