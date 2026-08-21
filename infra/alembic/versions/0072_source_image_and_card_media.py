"""Add source_image table and module_card.media_jsonb.

Revision ID: 0072
Revises: 0071
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0072"
down_revision: str | None = "0071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_image",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_page_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("image_order", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column("width_px", sa.Integer(), nullable=True),
        sa.Column("height_px", sa.Integer(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("alt_text", sa.Text(), nullable=True),
        sa.Column("nearby_text", sa.Text(), nullable=True),
        sa.Column("bbox_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("start_ms", sa.Integer(), nullable=True),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["source_document.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_page_id"],
            ["source_page.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_source_image_source_document_id",
        "source_image",
        ["source_document_id"],
    )
    op.create_index(
        "ix_source_image_source_page_id",
        "source_image",
        ["source_page_id"],
    )
    op.create_index(
        "ix_source_image_doc_sha256",
        "source_image",
        ["source_document_id", "content_sha256"],
    )
    op.add_column(
        "module_card",
        sa.Column("media_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("module_card", "media_jsonb")
    op.drop_index("ix_source_image_doc_sha256", table_name="source_image")
    op.drop_index("ix_source_image_source_page_id", table_name="source_image")
    op.drop_index("ix_source_image_source_document_id", table_name="source_image")
    op.drop_table("source_image")
