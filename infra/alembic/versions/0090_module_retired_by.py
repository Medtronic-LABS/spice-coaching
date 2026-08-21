"""Add module.retired_by hierarchy user reference.

Revision ID: 0090
Revises: 0089
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0090"
down_revision: str | None = "0089"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("module", sa.Column("retired_by", sa.BigInteger(), nullable=True))
    op.create_index("ix_module_retired_by", "module", ["retired_by"])


def downgrade() -> None:
    op.drop_index("ix_module_retired_by", table_name="module")
    op.drop_column("module", "retired_by")
