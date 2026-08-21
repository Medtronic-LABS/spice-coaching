"""Soft user refs: drop users FKs; stampers to nullable bigint.

Revision ID: 0087
Revises: 0086
Create Date: 2026-08-16

Stampers and relationship columns store ``users.id`` as soft bigints with no
FK. Legacy text/uuid stamper values are nulled (no backfill). Orphan retention
on user delete is intentional.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0087"
down_revision: str | None = "0086"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK_DROPS: list[tuple[str, str]] = [
    ("module", "fk_module_created_by_users"),
    ("module", "fk_module_published_by_users"),
    ("module", "fk_module_activated_by_users"),
    ("module", "fk_module_deactivated_by_users"),
    ("module_assignment", "fk_module_assignment_user_id_users"),
    ("document_assignment", "document_assignment_user_id_fkey"),
    ("user_upazila", "user_upazila_user_id_fkey"),
    ("users", "users_parent_id_fkey"),
]

_TEXT_STAMPERS: list[tuple[str, str, bool]] = [
    # table, column, was_not_null
    ("division", "created_by", True),
    ("division", "updated_by", True),
    ("district", "created_by", True),
    ("district", "updated_by", True),
    ("upazila", "created_by", True),
    ("upazila", "updated_by", True),
    ("users", "created_by", True),
    ("users", "updated_by", True),
    ("badge", "created_by", False),
    ("badge", "updated_by", False),
    ("config_threshold_change", "updated_by", True),
    ("file_upload", "uploaded_by", False),
]


def upgrade() -> None:
    for table, constraint in _FK_DROPS:
        op.drop_constraint(constraint, table, type_="foreignkey")

    for table, column, was_not_null in _TEXT_STAMPERS:
        # Legacy text actors cannot cast to bigint — null them. Drop NOT NULL first
        # so USING NULL does not violate the existing constraint (see 0070/0076).
        if was_not_null:
            op.alter_column(table, column, nullable=True)
        op.alter_column(
            table,
            column,
            existing_type=sa.Text(),
            type_=sa.BigInteger(),
            existing_nullable=True,
            nullable=True,
            postgresql_using="NULL",
        )

    op.alter_column(
        "module_family",
        "created_by",
        existing_type=sa.UUID(),
        type_=sa.BigInteger(),
        existing_nullable=True,
        nullable=True,
        postgresql_using="NULL",
    )


def downgrade() -> None:
    op.alter_column(
        "module_family",
        "created_by",
        existing_type=sa.BigInteger(),
        type_=sa.UUID(),
        nullable=True,
        postgresql_using="NULL",
    )

    for table, column, _was_not_null in reversed(_TEXT_STAMPERS):
        # Downgrade cannot restore previous string values; leave nullable.
        op.alter_column(
            table,
            column,
            existing_type=sa.BigInteger(),
            type_=sa.Text(),
            existing_nullable=True,
            nullable=True,
            postgresql_using="NULL",
        )

    op.create_foreign_key(
        "users_parent_id_fkey",
        "users",
        "users",
        ["parent_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "user_upazila_user_id_fkey",
        "user_upazila",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "document_assignment_user_id_fkey",
        "document_assignment",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_module_assignment_user_id_users",
        "module_assignment",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_module_deactivated_by_users",
        "module",
        "users",
        ["deactivated_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_module_activated_by_users",
        "module",
        "users",
        ["activated_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_module_published_by_users",
        "module",
        "users",
        ["published_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_module_created_by_users",
        "module",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
