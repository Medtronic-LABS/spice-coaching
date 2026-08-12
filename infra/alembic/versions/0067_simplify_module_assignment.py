"""Simplify module assignment to per-user rows only.

Revision ID: 0067
Revises: 0066
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0067"
down_revision: str | None = "0066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("TRUNCATE chw_module_assignment"))

    op.drop_index("uq_module_assignment_tenant", table_name="chw_module_assignment")
    op.drop_index(op.f("ix_chw_module_assignment_upazila"), table_name="chw_module_assignment")
    op.drop_constraint("uq_module_assignment_upazila", "chw_module_assignment", type_="unique")

    op.drop_column("chw_module_assignment", "assignment_type")
    op.drop_column("chw_module_assignment", "upazila")

    op.alter_column("chw_module_assignment", "user_id", existing_type=sa.BigInteger(), nullable=False)
    op.create_foreign_key(
        "fk_module_assignment_user_id_users",
        "chw_module_assignment",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.rename_table("chw_module_assignment", "module_assignment")
    op.execute(
        sa.text("ALTER INDEX ix_chw_module_assignment_tenant_id RENAME TO ix_module_assignment_tenant_id")
    )
    op.execute(
        sa.text("ALTER INDEX ix_chw_module_assignment_user_id RENAME TO ix_module_assignment_user_id")
    )


def downgrade() -> None:
    op.rename_table("module_assignment", "chw_module_assignment")
    op.execute(
        sa.text("ALTER INDEX ix_module_assignment_tenant_id RENAME TO ix_chw_module_assignment_tenant_id")
    )
    op.execute(
        sa.text("ALTER INDEX ix_module_assignment_user_id RENAME TO ix_chw_module_assignment_user_id")
    )

    op.drop_constraint("fk_module_assignment_user_id_users", "chw_module_assignment", type_="foreignkey")

    op.add_column(
        "chw_module_assignment",
        sa.Column("assignment_type", sa.String(length=50), nullable=False, server_default="individual"),
    )
    op.alter_column("chw_module_assignment", "assignment_type", server_default=None)
    op.add_column("chw_module_assignment", sa.Column("upazila", sa.String(length=100), nullable=True))

    op.alter_column("chw_module_assignment", "user_id", existing_type=sa.BigInteger(), nullable=True)

    op.create_unique_constraint(
        "uq_module_assignment_upazila",
        "chw_module_assignment",
        ["module_id", "upazila"],
    )
    op.create_index(
        op.f("ix_chw_module_assignment_upazila"),
        "chw_module_assignment",
        ["upazila"],
        unique=False,
    )
    op.create_index(
        "uq_module_assignment_tenant",
        "chw_module_assignment",
        ["module_id", "tenant_id"],
        unique=True,
        postgresql_where=sa.text("assignment_type = 'group'"),
    )
