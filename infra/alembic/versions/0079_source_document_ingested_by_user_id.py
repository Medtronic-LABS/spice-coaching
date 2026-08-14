"""Convert source_document.ingested_by from UUID to BigInt user id.

Revision ID: 0079
Revises: 0078
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0079"
down_revision: str | None = "0078"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Legacy UUID actors cannot cast to BigInt — null them (column was unused).
    op.execute(sa.text("UPDATE source_document SET ingested_by = NULL"))
    op.alter_column(
        "source_document",
        "ingested_by",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using="NULL",
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE source_document SET ingested_by = NULL"))
    op.alter_column(
        "source_document",
        "ingested_by",
        existing_type=sa.BigInteger(),
        type_=postgresql.UUID(as_uuid=True),
        existing_nullable=True,
        postgresql_using="NULL",
    )
