"""Normalize users.role into role lookup table with role_id FK.

Revision ID: 0085
Revises: 0084
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0085"
down_revision: str | None = "0084"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENFORCE_USERS_HIERARCHY_ROLE_ID = """
CREATE OR REPLACE FUNCTION enforce_users_hierarchy()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    new_role_code text;
    parent_role_code text;
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

    SELECT r.code INTO new_role_code
    FROM role r
    WHERE r.id = NEW.role_id;

    IF new_role_code IS NULL THEN
        RAISE EXCEPTION 'hierarchy_role_mismatch: role_id % not found', NEW.role_id;
    END IF;

    IF new_role_code = 'AREA_MANAGER' THEN
        IF NEW.parent_id IS NOT NULL THEN
            RAISE EXCEPTION
                'hierarchy_parent_invalid: AREA_MANAGER must have parent_id NULL';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.parent_id IS NULL THEN
        RAISE EXCEPTION
            'hierarchy_parent_invalid: role % requires a parent_id', new_role_code;
    END IF;

    SELECT r.code, u.district_id, u.tenant_id
    INTO parent_role_code, parent_district_id, parent_tenant_id
    FROM users u
    JOIN role r ON r.id = u.role_id
    WHERE u.id = NEW.parent_id;

    IF parent_role_code IS NULL THEN
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

    IF new_role_code = 'PO' THEN
        expected_parent_role := 'AREA_MANAGER';
    ELSIF new_role_code = 'SHASTIYA_KORMI' THEN
        expected_parent_role := 'PO';
    ELSE
        RAISE EXCEPTION 'hierarchy_role_mismatch: unsupported role %', new_role_code;
    END IF;

    IF parent_role_code <> expected_parent_role THEN
        RAISE EXCEPTION
            'hierarchy_parent_invalid: role % requires parent role %, got %',
            new_role_code, expected_parent_role, parent_role_code;
    END IF;

    RETURN NEW;
END;
$$;
"""

_ENFORCE_USERS_HIERARCHY_TEXT_ROLE = """
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

    IF NEW.role = 'PO' THEN
        expected_parent_role := 'AREA_MANAGER';
    ELSIF NEW.role = 'SHASTIYA_KORMI' THEN
        expected_parent_role := 'PO';
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


def upgrade() -> None:
    op.create_table(
        "role",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.UniqueConstraint("code", name="uq_role_code"),
    )
    op.execute(
        """
        INSERT INTO role (code) VALUES
            ('AREA_MANAGER'),
            ('PO'),
            ('SHASTIYA_KORMI')
        """
    )

    op.add_column("users", sa.Column("role_id", sa.BigInteger(), nullable=True))
    op.execute(
        """
        UPDATE users AS u
        SET role_id = r.id
        FROM role AS r
        WHERE r.code = u.role
        """
    )
    op.alter_column("users", "role_id", nullable=False)
    op.create_foreign_key(
        "fk_users_role_id_role",
        "users",
        "role",
        ["role_id"],
        ["id"],
    )
    op.create_index("ix_users_role_id", "users", ["role_id"], unique=False)

    op.execute("DROP TRIGGER IF EXISTS trg_users_hierarchy ON users")
    op.drop_constraint("ck_users_parent_nullability", "users", type_="check")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_column("users", "role")

    op.execute(_ENFORCE_USERS_HIERARCHY_ROLE_ID)
    op.execute(
        """
        CREATE TRIGGER trg_users_hierarchy
        BEFORE INSERT OR UPDATE OF role_id, parent_id, district_id, tenant_id
        ON users
        FOR EACH ROW
        EXECUTE FUNCTION enforce_users_hierarchy();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_users_hierarchy ON users")

    op.add_column("users", sa.Column("role", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE users AS u
        SET role = r.code
        FROM role AS r
        WHERE r.id = u.role_id
        """
    )
    op.alter_column("users", "role", nullable=False)

    op.drop_index("ix_users_role_id", table_name="users")
    op.drop_constraint("fk_users_role_id_role", "users", type_="foreignkey")
    op.drop_column("users", "role_id")

    op.create_index("ix_users_role", "users", ["role"], unique=False)
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('AREA_MANAGER', 'PO', 'SHASTIYA_KORMI')",
    )
    op.create_check_constraint(
        "ck_users_parent_nullability",
        "users",
        "(role = 'AREA_MANAGER' AND parent_id IS NULL) OR "
        "(role <> 'AREA_MANAGER' AND parent_id IS NOT NULL)",
    )

    op.execute(_ENFORCE_USERS_HIERARCHY_TEXT_ROLE)
    op.execute(
        """
        CREATE TRIGGER trg_users_hierarchy
        BEFORE INSERT OR UPDATE OF role, parent_id, district_id, tenant_id
        ON users
        FOR EACH ROW
        EXECUTE FUNCTION enforce_users_hierarchy();
        """
    )
    op.drop_table("role")
