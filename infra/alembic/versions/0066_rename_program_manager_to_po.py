"""Rename hierarchy role PROGRAM_MANAGER → PO and assignment_type pm_sk → po_sk.

Revision ID: 0066
Revises: 0065
Create Date: 2026-08-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0066"
down_revision: str | None = "0065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENFORCE_USERS_HIERARCHY_PO = """
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

_ENFORCE_USERS_HIERARCHY_PROGRAM_MANAGER = """
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


def upgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.execute("UPDATE users SET role = 'PO' WHERE role = 'PROGRAM_MANAGER'")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('AREA_MANAGER', 'PO', 'SHASTIYA_KORMI')",
    )
    op.execute(_ENFORCE_USERS_HIERARCHY_PO)
    op.execute("UPDATE chw_module_assignment SET assignment_type = 'po_sk' WHERE assignment_type = 'pm_sk'")
    op.execute("UPDATE chw_video_assignment SET assignment_type = 'po_sk' WHERE assignment_type = 'pm_sk'")


def downgrade() -> None:
    op.execute("UPDATE chw_module_assignment SET assignment_type = 'pm_sk' WHERE assignment_type = 'po_sk'")
    op.execute("UPDATE chw_video_assignment SET assignment_type = 'pm_sk' WHERE assignment_type = 'po_sk'")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.execute("UPDATE users SET role = 'PROGRAM_MANAGER' WHERE role = 'PO'")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('AREA_MANAGER', 'PROGRAM_MANAGER', 'SHASTIYA_KORMI')",
    )
    op.execute(_ENFORCE_USERS_HIERARCHY_PROGRAM_MANAGER)
