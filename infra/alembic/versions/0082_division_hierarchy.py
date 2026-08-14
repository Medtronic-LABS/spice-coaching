"""Add division table and nullable district.division_id.

Revision ID: 0082
Revises: 0081

Follow-up migration 0083 should set district.division_id NOT NULL after backfill.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0082"
down_revision: str | None = "0081"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "division",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
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
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
    )
    op.create_index("ix_division_tenant_id", "division", ["tenant_id"], unique=False)

    op.add_column("district", sa.Column("division_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_district_division_id",
        "district",
        "division",
        ["division_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_district_division_id", "district", ["division_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_district_division_id", table_name="district")
    op.drop_constraint("fk_district_division_id", "district", type_="foreignkey")
    op.drop_column("district", "division_id")
    op.drop_index("ix_division_tenant_id", table_name="division")
    op.drop_table("division")
