"""Canonical platform HTTP path templates and v1 role→route grant matrix.

Path templates are relative to ``api_root`` with a leading slash and FastAPI
``{param}`` placeholders. One template covers all HTTP methods on that path.

Seeded by Alembic and checked by the route-inventory test so the catalog
cannot drift from the FastAPI app.
"""

from __future__ import annotations

from platform_service.db.models.hierarchy_user import (
    ROLE_AREA_MANAGER,
    ROLE_PO,
    ROLE_SHASTIYA_KORMI,
    ROLE_SUPER_ADMIN,
)

ADMIN_PATH_TEMPLATES: frozenset[str] = frozenset(
    {
        "/admin/assignments",
        "/admin/assignments/{module_id}/users",
        "/admin/badges",
        "/admin/badges/{badge_id}",
        "/admin/configs",
        "/admin/configs/{key}",
        "/admin/configs/{key}/changes",
        "/admin/districts",
        "/admin/districts/{district_id}",
        "/admin/divisions",
        "/admin/divisions/{division_id}",
        "/admin/document-assignments",
        "/admin/document-assignments/{source_document_id}/users",
        "/admin/files",
        "/admin/files/presigned-url",
        "/admin/hierarchy/import",
        "/admin/hierarchy/users",
        "/admin/hierarchy/users/{user_id}",
        "/admin/ingest",
        "/admin/ingest/batches/{batch_id}",
        "/admin/ingest/batches/{batch_id}/retry",
        "/admin/ingest/modules/{module_id}/override-merge",
        "/admin/ingest/modules/{module_id}/split-merge",
        "/admin/ingest/upload",
        "/admin/ingestion-runs",
        "/admin/ingestion-runs/{run_id}",
        "/admin/knowledge/upload",
        "/admin/knowledge/uploaders",
        "/admin/knowledge/{source_document_id}",
        "/admin/modules",
        "/admin/modules/domains",
        "/admin/modules/{module_id}",
        "/admin/modules/{module_id}/deactivate",
        "/admin/modules/{module_id}/publish",
        "/admin/modules/{module_id}/reactivate",
        "/admin/prompts",
        "/admin/prompts/{template_id}",
        "/admin/prompts/{template_id}/preview",
        "/admin/prompts/{template_id}/variables",
        "/admin/prompts/{template_id}/versions",
        "/admin/prompts/{template_id}/versions/{version}",
        "/admin/prompts/{template_id}/versions/{version}/activate",
        "/admin/source-documents",
        "/admin/source-documents/{source_document_id}",
        "/admin/source-documents/{source_document_id}/thumbnail",
        "/admin/upazilas",
        "/admin/upazilas/{upazila_id}",
    }
)

DASHBOARD_PATH_TEMPLATES: frozenset[str] = frozenset(
    {
        "/dashboard/digital-help-modules",
        "/dashboard/digital-help-modules/{module_id}/questions",
        "/dashboard/digital-help-modules/{module_id}/requests",
        "/dashboard/document-usage",
        "/dashboard/module-creation-suggestions",
        "/dashboard/module-creation-suggestions/{suggestion_id}",
        "/dashboard/module-demand-summary",
        "/dashboard/published-module-completions",
        "/dashboard/team-activity",
        "/dashboard/team-activity/users/{user_id}/questions",
    }
)

SYNC_PATH_TEMPLATES: frozenset[str] = frozenset(
    {
        "/sync/badges",
        "/sync/card-embeddings",
        "/sync/chat-faqs",
        "/sync/config",
        "/sync/gaps",
        "/sync/modules",
        "/sync/presigned-urls",
        "/sync/source-documents",
        "/sync/triggers",
        "/sync/video-progress",
    }
)

DEVICE_PATH_TEMPLATES: frozenset[str] = frozenset(
    {
        "/coaching/rag-query",
        "/coaching/local-rag-query",
        "/morning/cards",
        "/telemetry/events",
    }
    | SYNC_PATH_TEMPLATES
)

ALL_PATH_TEMPLATES: frozenset[str] = ADMIN_PATH_TEMPLATES | DASHBOARD_PATH_TEMPLATES | DEVICE_PATH_TEMPLATES

ROLE_ROUTE_GRANTS: dict[str, frozenset[str]] = {
    ROLE_AREA_MANAGER: ADMIN_PATH_TEMPLATES | DASHBOARD_PATH_TEMPLATES,
    ROLE_PO: DASHBOARD_PATH_TEMPLATES | DEVICE_PATH_TEMPLATES,
    ROLE_SHASTIYA_KORMI: DEVICE_PATH_TEMPLATES,
    ROLE_SUPER_ADMIN: ALL_PATH_TEMPLATES - SYNC_PATH_TEMPLATES,
}


def path_templates_for_role(role_code: str) -> frozenset[str]:
    """Return seeded path templates granted to ``role_code`` (empty if unknown)."""
    return ROLE_ROUTE_GRANTS.get(role_code, frozenset())
