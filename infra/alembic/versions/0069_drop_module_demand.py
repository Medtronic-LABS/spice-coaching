"""Drop admin module demand snapshot table and related seeds.

Revision ID: 0069
Revises: 0068
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0069"
down_revision: str | None = "0068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM prompt_template WHERE template_id = 'module-demand-summary'")
    op.execute("DELETE FROM config_threshold WHERE key = 'module_demand_top_k'")
    op.drop_table("module_demand_summary")


def downgrade() -> None:
    op.create_table(
        "module_demand_summary",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_module_demand_summary_tenant"),
    )
    op.create_index(
        "ix_module_demand_summary_tenant",
        "module_demand_summary",
        ["tenant_id"],
    )
    op.execute(
        """
        INSERT INTO config_threshold (tenant_id, version, key, value_json, title, description)
        VALUES (
            0, 1, 'module_demand_top_k', '10'::jsonb,
            'Module Demand Top K',
            'Number of top requested modules shown in the admin module demand summary.'
        )
        ON CONFLICT ON CONSTRAINT uq_config_threshold_tenant_key DO NOTHING
        """
    )
