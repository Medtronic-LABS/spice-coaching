"""Add ingestion_run_generation_counts for frozen list/detail tallies.

Revision ID: 0083
Revises: 0082
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0083"
down_revision: str | None = "0082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_run_generation_counts",
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generated_module_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generated_card_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generated_quiz_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_run.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["source_document.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ingestion_run_id", "source_document_id"),
    )


def downgrade() -> None:
    op.drop_table("ingestion_run_generation_counts")
