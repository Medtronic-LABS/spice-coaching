"""Seed assign-to-all admin routes into api_route and role_route_access.

Revision ID: 0107
Revises: 0106
Create Date: 2026-11-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from platform_service.auth.api_route_catalog import ROLE_ROUTE_GRANTS
from platform_service.db.models.hierarchy_user import ROLE_AREA_MANAGER, ROLE_SUPER_ADMIN

revision: str = "0107"
down_revision: str | None = "0106"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PATHS = (
    "/admin/modules/{module_id}/assign-to-all",
    "/admin/source-documents/{source_document_id}/assign-to-all",
)


def upgrade() -> None:
    bind = op.get_bind()
    role_rows = bind.execute(sa.text("SELECT id, code FROM role")).mappings().all()
    role_id_by_code = {row["code"]: row["id"] for row in role_rows}

    for path in _PATHS:
        existing = bind.execute(
            sa.text("SELECT id FROM api_route WHERE path_template = :path"),
            {"path": path},
        ).scalar_one_or_none()
        if existing is None:
            bind.execute(
                sa.text("INSERT INTO api_route (path_template) VALUES (:path)"),
                {"path": path},
            )
        route_id = bind.execute(
            sa.text("SELECT id FROM api_route WHERE path_template = :path"),
            {"path": path},
        ).scalar_one()

        for role_code in (ROLE_AREA_MANAGER, ROLE_SUPER_ADMIN):
            if path not in ROLE_ROUTE_GRANTS.get(role_code, frozenset()):
                continue
            bind.execute(
                sa.text(
                    """
                    INSERT INTO role_route_access (role_id, api_route_id)
                    VALUES (:role_id, :api_route_id)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"role_id": role_id_by_code[role_code], "api_route_id": route_id},
            )


def downgrade() -> None:
    bind = op.get_bind()
    for path in _PATHS:
        route_id = bind.execute(
            sa.text("SELECT id FROM api_route WHERE path_template = :path"),
            {"path": path},
        ).scalar_one_or_none()
        if route_id is None:
            continue
        bind.execute(
            sa.text("DELETE FROM role_route_access WHERE api_route_id = :route_id"),
            {"route_id": route_id},
        )
        bind.execute(
            sa.text("DELETE FROM api_route WHERE id = :route_id"),
            {"route_id": route_id},
        )
