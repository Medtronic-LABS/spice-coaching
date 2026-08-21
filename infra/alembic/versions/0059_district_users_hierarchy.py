"""Add district and users hierarchy tables.

Revision ID: 0059
Revises: 0058
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0059"
down_revision: str | None = "0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "district",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
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
    )
    op.create_index("ix_district_tenant_id", "district", ["tenant_id"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("district_id", sa.BigInteger(), nullable=False),
        sa.Column("upazila", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(["parent_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["district_id"], ["district.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "role IN ('AREA_MANAGER', 'PROGRAM_MANAGER', 'SHASTIYA_KORMI')",
            name="ck_users_role",
        ),
        sa.CheckConstraint(
            "(role = 'AREA_MANAGER' AND parent_id IS NULL) OR "
            "(role <> 'AREA_MANAGER' AND parent_id IS NOT NULL)",
            name="ck_users_parent_nullability",
        ),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"], unique=False)
    op.create_index("ix_users_district_id", "users", ["district_id"], unique=False)
    op.create_index("ix_users_parent_id", "users", ["parent_id"], unique=False)
    op.create_index("ix_users_role", "users", ["role"], unique=False)

    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_users_hierarchy()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            parent_role text;
            parent_district_id bigint;
            parent_tenant_id bigint;
            district_tenant_id bigint;
            expected_parent_role text;
        BEGIN
            SELECT d.tenant_id INTO district_tenant_id
            FROM district d
            WHERE d.id = NEW.district_id;

            IF district_tenant_id IS NULL THEN
                RAISE EXCEPTION 'hierarchy_parent_invalid: district % not found', NEW.district_id;
            END IF;

            IF district_tenant_id <> NEW.tenant_id THEN
                RAISE EXCEPTION
                    'hierarchy_parent_invalid: user tenant_id % does not match district tenant_id %',
                    NEW.tenant_id, district_tenant_id;
            END IF;

            IF NEW.role = 'AREA_MANAGER' THEN
                IF NEW.parent_id IS NOT NULL THEN
                    RAISE EXCEPTION
                        'hierarchy_parent_invalid: AREA_MANAGER must have parent_id NULL';
                END IF;
                RETURN NEW;
            END IF;

            IF NEW.parent_id IS NULL THEN
                RAISE EXCEPTION
                    'hierarchy_parent_invalid: role % requires a parent_id', NEW.role;
            END IF;

            SELECT u.role, u.district_id, u.tenant_id
            INTO parent_role, parent_district_id, parent_tenant_id
            FROM users u
            WHERE u.id = NEW.parent_id;

            IF parent_role IS NULL THEN
                RAISE EXCEPTION
                    'hierarchy_parent_invalid: parent user % not found', NEW.parent_id;
            END IF;

            IF parent_district_id <> NEW.district_id THEN
                RAISE EXCEPTION
                    'hierarchy_parent_invalid: parent district_id % does not match child district_id %',
                    parent_district_id, NEW.district_id;
            END IF;

            IF parent_tenant_id <> NEW.tenant_id THEN
                RAISE EXCEPTION
                    'hierarchy_parent_invalid: parent tenant_id % does not match child tenant_id %',
                    parent_tenant_id, NEW.tenant_id;
            END IF;

            IF NEW.role = 'PROGRAM_MANAGER' THEN
                expected_parent_role := 'AREA_MANAGER';
            ELSIF NEW.role = 'SHASTIYA_KORMI' THEN
                expected_parent_role := 'PROGRAM_MANAGER';
            ELSE
                RAISE EXCEPTION 'hierarchy_role_mismatch: unsupported role %', NEW.role;
            END IF;

            IF parent_role <> expected_parent_role THEN
                RAISE EXCEPTION
                    'hierarchy_parent_invalid: role % requires parent role %, got %',
                    NEW.role, expected_parent_role, parent_role;
            END IF;

            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_users_hierarchy
        BEFORE INSERT OR UPDATE OF role, parent_id, district_id, tenant_id
        ON users
        FOR EACH ROW
        EXECUTE FUNCTION enforce_users_hierarchy();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_users_hierarchy ON users")
    op.execute("DROP FUNCTION IF EXISTS enforce_users_hierarchy()")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_parent_id", table_name="users")
    op.drop_index("ix_users_district_id", table_name="users")
    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_district_tenant_id", table_name="district")
    op.drop_table("district")
