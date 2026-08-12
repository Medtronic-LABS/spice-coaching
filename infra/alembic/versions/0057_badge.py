"""Add badge catalog and badge_module junction.

Revision ID: 0057
Revises: 0056
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0057"
down_revision: str | None = "0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "badge",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("image_storage_path", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_badge_domain", "badge", ["domain"], unique=False)
    op.create_index("ix_badge_status", "badge", ["status"], unique=False)
    op.execute(
        """
        CREATE UNIQUE INDEX uq_badge_name_active
        ON badge (name)
        WHERE status = 'active'
        """
    )

    op.create_table(
        "badge_module",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "badge_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("badge.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "module_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("module.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("badge_id", "module_id", name="uq_badge_module_pair"),
    )
    op.create_index("ix_badge_module_badge_id", "badge_module", ["badge_id"], unique=False)
    op.create_index("ix_badge_module_module_id", "badge_module", ["module_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_badge_module_module_id", table_name="badge_module")
    op.drop_index("ix_badge_module_badge_id", table_name="badge_module")
    op.drop_table("badge_module")
    op.execute("DROP INDEX IF EXISTS uq_badge_name_active")
    op.drop_index("ix_badge_status", table_name="badge")
    op.drop_index("ix_badge_domain", table_name="badge")
    op.drop_table("badge")
