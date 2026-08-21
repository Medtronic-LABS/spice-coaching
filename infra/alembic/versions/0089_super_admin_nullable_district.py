"""Allow SUPER_ADMIN users.district_id NULL for auth auto-provision.

Revision ID: 0089
Revises: 0088
Create Date: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0089"
down_revision: str | None = "0088"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENFORCE_USERS_HIERARCHY_NULLABLE_SUPER_ADMIN_DISTRICT = """
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
    SELECT r.code INTO new_role_code
    FROM role r
    WHERE r.id = NEW.role_id;

    IF new_role_code IS NULL THEN
        RAISE EXCEPTION 'hierarchy_role_mismatch: role_id % not found', NEW.role_id;
    END IF;

    IF new_role_code = 'SUPER_ADMIN' THEN
        IF NEW.parent_id IS NOT NULL THEN
            RAISE EXCEPTION
                'hierarchy_parent_invalid: SUPER_ADMIN must have parent_id NULL';
        END IF;
        IF NEW.district_id IS NULL THEN
            RETURN NEW;
        END IF;
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
        RETURN NEW;
    END IF;

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

# Restores 0086 body (SUPER_ADMIN root role, district always required).
_ENFORCE_USERS_HIERARCHY_REQUIRED_DISTRICT = """
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

    IF new_role_code IN ('AREA_MANAGER', 'SUPER_ADMIN') THEN
        IF NEW.parent_id IS NOT NULL THEN
            RAISE EXCEPTION
                'hierarchy_parent_invalid: % must have parent_id NULL', new_role_code;
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


def upgrade() -> None:
    op.alter_column(
        "users",
        "district_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.execute(_ENFORCE_USERS_HIERARCHY_NULLABLE_SUPER_ADMIN_DISTRICT)


def downgrade() -> None:
    op.execute("DELETE FROM users WHERE district_id IS NULL")
    op.alter_column(
        "users",
        "district_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.execute(_ENFORCE_USERS_HIERARCHY_REQUIRED_DISTRICT)
