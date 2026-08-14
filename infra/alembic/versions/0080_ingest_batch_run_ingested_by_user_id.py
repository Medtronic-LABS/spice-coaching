"""Rename ingest_batch/ingestion_run.triggered_by → ingested_by (BigInt).

Revision ID: 0080
Revises: 0079
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0080"
down_revision: str | None = "0079"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Legacy UUID actors cannot cast to BigInt — null them (columns were unused).
    op.execute(sa.text("UPDATE ingest_batch SET triggered_by = NULL"))
    op.alter_column(
        "ingest_batch",
        "triggered_by",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using="NULL",
    )
    op.alter_column("ingest_batch", "triggered_by", new_column_name="ingested_by")

    op.execute(sa.text("UPDATE ingestion_run SET triggered_by = NULL"))
    op.alter_column(
        "ingestion_run",
        "triggered_by",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using="NULL",
    )
    op.alter_column("ingestion_run", "triggered_by", new_column_name="ingested_by")


def downgrade() -> None:
    op.execute(sa.text("UPDATE ingest_batch SET ingested_by = NULL"))
    op.alter_column(
        "ingest_batch",
        "ingested_by",
        existing_type=sa.BigInteger(),
        type_=postgresql.UUID(as_uuid=True),
        existing_nullable=True,
        postgresql_using="NULL",
    )
    op.alter_column("ingest_batch", "ingested_by", new_column_name="triggered_by")

    op.execute(sa.text("UPDATE ingestion_run SET ingested_by = NULL"))
    op.alter_column(
        "ingestion_run",
        "ingested_by",
        existing_type=sa.BigInteger(),
        type_=postgresql.UUID(as_uuid=True),
        existing_nullable=True,
        postgresql_using="NULL",
    )
    op.alter_column("ingestion_run", "ingested_by", new_column_name="triggered_by")
