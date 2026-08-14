"""Add module.created_by hierarchy user reference.

Revision ID: 0074
Revises: 0073
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0074"
down_revision: str | None = "0073"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("module", sa.Column("created_by", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_module_created_by_users",
        "module",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_module_created_by", "module", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_module_created_by", table_name="module")
    op.drop_constraint("fk_module_created_by_users", "module", type_="foreignkey")
    op.drop_column("module", "created_by")
