"""Convert module lifecycle actor columns to hierarchy user references.

Revision ID: 0076
Revises: 0075
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0076"
down_revision: str | None = "0075"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Legacy UUID actor ids cannot map to hierarchy users — null them before type change.
    op.execute(sa.text("UPDATE module SET deactivated_by = NULL"))
    op.alter_column(
        "module",
        "deactivated_by",
        existing_type=sa.UUID(),
        type_=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using="NULL",
    )
    op.create_foreign_key(
        "fk_module_deactivated_by_users",
        "module",
        "users",
        ["deactivated_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_module_deactivated_by", "module", ["deactivated_by"])

    op.alter_column("module", "reactivated_by", new_column_name="activated_by")
    op.execute(sa.text("UPDATE module SET activated_by = NULL"))
    op.alter_column(
        "module",
        "activated_by",
        existing_type=sa.UUID(),
        type_=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using="NULL",
    )
    op.create_foreign_key(
        "fk_module_activated_by_users",
        "module",
        "users",
        ["activated_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_module_activated_by", "module", ["activated_by"])


def downgrade() -> None:
    op.drop_index("ix_module_activated_by", table_name="module")
    op.drop_constraint("fk_module_activated_by_users", "module", type_="foreignkey")
    op.alter_column(
        "module",
        "activated_by",
        existing_type=sa.BigInteger(),
        type_=sa.UUID(),
        existing_nullable=True,
        postgresql_using="NULL",
    )
    op.alter_column("module", "activated_by", new_column_name="reactivated_by")

    op.drop_index("ix_module_deactivated_by", table_name="module")
    op.drop_constraint("fk_module_deactivated_by_users", "module", type_="foreignkey")
    op.alter_column(
        "module",
        "deactivated_by",
        existing_type=sa.BigInteger(),
        type_=sa.UUID(),
        existing_nullable=True,
        postgresql_using="NULL",
    )
