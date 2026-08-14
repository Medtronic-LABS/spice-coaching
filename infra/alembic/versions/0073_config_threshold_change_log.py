"""Config threshold change log — log-only value storage.

Revision ID: 0073
Revises: 0072
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0073"
down_revision: str | None = "0072"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "config_threshold_change",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("config_threshold_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("previous_value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("current_value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["config_threshold_id"],
            ["config_threshold.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_config_threshold_change_tenant_key_updated",
        "config_threshold_change",
        ["tenant_id", "key", sa.text("updated_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_config_threshold_change_config_threshold_id",
        "config_threshold_change",
        ["config_threshold_id"],
    )

    op.execute(
        """
        INSERT INTO config_threshold_change (
            tenant_id,
            config_threshold_id,
            key,
            previous_value_json,
            current_value_json,
            version,
            updated_by,
            updated_at
        )
        SELECT
            tenant_id,
            id,
            key,
            NULL,
            value_json,
            version,
            'migration',
            updated_at
        FROM config_threshold
        """
    )

    op.drop_column("config_threshold", "value_json")
    op.drop_column("config_threshold", "version")


def downgrade() -> None:
    op.add_column(
        "config_threshold",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "config_threshold",
        sa.Column("value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.execute(
        """
        UPDATE config_threshold AS ct
        SET
            value_json = latest.current_value_json,
            version = latest.version
        FROM (
            SELECT DISTINCT ON (config_threshold_id)
                config_threshold_id,
                current_value_json,
                version
            FROM config_threshold_change
            ORDER BY config_threshold_id, updated_at DESC, id DESC
        ) AS latest
        WHERE ct.id = latest.config_threshold_id
        """
    )

    op.alter_column("config_threshold", "value_json", nullable=False)
    op.alter_column("config_threshold", "version", server_default=None)

    op.drop_index("ix_config_threshold_change_config_threshold_id", table_name="config_threshold_change")
    op.drop_index("ix_config_threshold_change_tenant_key_updated", table_name="config_threshold_change")
    op.drop_table("config_threshold_change")
