"""Convert source_document.uploaded_by to BigInt user id; add updated_by.

Revision ID: 0070
Revises: 0069
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0070"
down_revision: str | None = "0069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Legacy text actors (usernames / "admin") cannot cast to BigInt — null them.
    op.execute(sa.text("UPDATE source_document SET uploaded_by = NULL"))
    op.alter_column(
        "source_document",
        "uploaded_by",
        existing_type=sa.Text(),
        type_=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using="NULL",
    )
    op.add_column("source_document", sa.Column("updated_by", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("source_document", "updated_by")
    op.alter_column(
        "source_document",
        "uploaded_by",
        existing_type=sa.BigInteger(),
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="uploaded_by::text",
    )
