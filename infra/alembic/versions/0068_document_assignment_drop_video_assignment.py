"""Create document_assignment and drop chw_video_assignment.

Revision ID: 0068
Revises: 0067
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0068"
down_revision: str | None = "0067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_assignment",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_document_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("assigned_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
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
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_document_id",
            "user_id",
            name="uq_document_assignment_user",
        ),
    )
    op.create_index(
        op.f("ix_document_assignment_tenant_id"),
        "document_assignment",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_assignment_user_id"),
        "document_assignment",
        ["user_id"],
        unique=False,
    )

    op.drop_index(op.f("ix_chw_video_assignment_upazila"), table_name="chw_video_assignment")
    op.drop_index(op.f("ix_chw_video_assignment_user_id"), table_name="chw_video_assignment")
    op.drop_index(op.f("ix_chw_video_assignment_tenant_id"), table_name="chw_video_assignment")
    op.drop_table("chw_video_assignment")


def downgrade() -> None:
    op.create_table(
        "chw_video_assignment",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_document_id", sa.UUID(), nullable=False),
        sa.Column("assignment_type", sa.String(length=50), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("upazila", sa.String(length=100), nullable=True),
        sa.Column("assigned_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["source_document.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_document_id",
            "tenant_id",
            name="uq_video_assignment_tenant",
        ),
        sa.UniqueConstraint(
            "source_document_id",
            "user_id",
            name="uq_video_assignment_user",
        ),
        sa.UniqueConstraint(
            "source_document_id",
            "upazila",
            name="uq_video_assignment_upazila",
        ),
    )
    op.create_index(
        op.f("ix_chw_video_assignment_tenant_id"),
        "chw_video_assignment",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chw_video_assignment_user_id"),
        "chw_video_assignment",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chw_video_assignment_upazila"),
        "chw_video_assignment",
        ["upazila"],
        unique=False,
    )

    op.drop_index(op.f("ix_document_assignment_user_id"), table_name="document_assignment")
    op.drop_index(op.f("ix_document_assignment_tenant_id"), table_name="document_assignment")
    op.drop_table("document_assignment")
