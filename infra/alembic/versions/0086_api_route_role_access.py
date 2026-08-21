"""Add api_route catalog and role_route_access grants.

Revision ID: 0086
Revises: 0085
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from platform_service.auth.api_route_catalog import ALL_PATH_TEMPLATES, ROLE_ROUTE_GRANTS

revision: str = "0086"
down_revision: str | None = "0085"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENFORCE_USERS_HIERARCHY_WITH_SUPER_ADMIN = """
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

# Restores the 0085 role_id trigger body (no SUPER_ADMIN root role).
_ENFORCE_USERS_HIERARCHY_WITHOUT_SUPER_ADMIN = """
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


def upgrade() -> None:
    op.execute("INSERT INTO role (code) VALUES ('SUPER_ADMIN') ON CONFLICT (code) DO NOTHING")
    op.execute(_ENFORCE_USERS_HIERARCHY_WITH_SUPER_ADMIN)

    op.create_table(
        "api_route",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("path_template", sa.Text(), nullable=False),
        sa.UniqueConstraint("path_template", name="uq_api_route_path_template"),
    )
    op.create_table(
        "role_route_access",
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("api_route_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["api_route_id"], ["api_route.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "api_route_id"),
    )
    op.create_index(
        "ix_role_route_access_role_id",
        "role_route_access",
        ["role_id"],
    )

    templates = sorted(ALL_PATH_TEMPLATES)
    api_route = sa.table(
        "api_route",
        sa.column("id", sa.BigInteger),
        sa.column("path_template", sa.Text),
    )
    op.bulk_insert(
        api_route,
        [{"path_template": path} for path in templates],
    )

    bind = op.get_bind()
    role_rows = bind.execute(sa.text("SELECT id, code FROM role")).mappings().all()
    role_id_by_code = {row["code"]: row["id"] for row in role_rows}
    route_rows = bind.execute(sa.text("SELECT id, path_template FROM api_route")).mappings().all()
    route_id_by_path = {row["path_template"]: row["id"] for row in route_rows}

    grant_rows: list[dict[str, int]] = []
    for role_code, paths in ROLE_ROUTE_GRANTS.items():
        role_id = role_id_by_code[role_code]
        for path in paths:
            grant_rows.append(
                {
                    "role_id": role_id,
                    "api_route_id": route_id_by_path[path],
                }
            )

    role_route_access = sa.table(
        "role_route_access",
        sa.column("role_id", sa.BigInteger),
        sa.column("api_route_id", sa.BigInteger),
    )
    op.bulk_insert(role_route_access, grant_rows)


def downgrade() -> None:
    op.drop_index("ix_role_route_access_role_id", table_name="role_route_access")
    op.drop_table("role_route_access")
    op.drop_table("api_route")
    op.execute(_ENFORCE_USERS_HIERARCHY_WITHOUT_SUPER_ADMIN)
    # SUPER_ADMIN role row is intentionally left in place.
