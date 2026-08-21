"""Add module.published_by hierarchy user reference.

Revision ID: 0075
Revises: 0074
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0075"
down_revision: str | None = "0074"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("module", sa.Column("published_by", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_module_published_by_users",
        "module",
        "users",
        ["published_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_module_published_by", "module", ["published_by"])


def downgrade() -> None:
    op.drop_index("ix_module_published_by", table_name="module")
    op.drop_constraint("fk_module_published_by_users", "module", type_="foreignkey")
    op.drop_column("module", "published_by")
