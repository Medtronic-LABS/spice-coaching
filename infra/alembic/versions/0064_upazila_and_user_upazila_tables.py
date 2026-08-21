"""Create upazila and user_upazila tables, remove upazila column from users.

Revision ID: 0064
Revises: 0063
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0064"
down_revision: str | None = "0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "upazila",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("district_id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
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
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["district_id"], ["district.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_upazila_tenant_id", "upazila", ["tenant_id"], unique=False)
    op.create_index("ix_upazila_district_id", "upazila", ["district_id"], unique=False)

    op.create_table(
        "user_upazila",
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("upazila_id", sa.BigInteger(), primary_key=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["upazila_id"], ["upazila.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_upazila_user_id", "user_upazila", ["user_id"], unique=False)
    op.create_index("ix_user_upazila_upazila_id", "user_upazila", ["upazila_id"], unique=False)

    op.drop_column("users", "upazila")


def downgrade() -> None:
    op.add_column("users", sa.Column("upazila", sa.Text(), nullable=True))
    op.drop_index("ix_user_upazila_upazila_id", table_name="user_upazila")
    op.drop_index("ix_user_upazila_user_id", table_name="user_upazila")
    op.drop_table("user_upazila")
    op.drop_index("ix_upazila_district_id", table_name="upazila")
    op.drop_index("ix_upazila_tenant_id", table_name="upazila")
    op.drop_table("upazila")
