"""Document-usage hierarchy helpers (re-exports from dashboard_hierarchy).

Kept for import compatibility. New call sites should prefer
``platform_service.services.dashboard_hierarchy``.
"""

from __future__ import annotations

from platform_service.services.dashboard_hierarchy import (
    OrgUser,
    apply_document_usage_filters,
    filter_users_by_chw_ids,
    focus_subtree_ids,
    is_hierarchy_scoped_role,
    org_user_index,
    resolve_geography_chw_ids,
    resolve_users_by_geography_ids,
    resolve_users_by_geography_names,
    resolve_visible_chw_ids,
    user_display,
)

__all__ = [
    "OrgUser",
    "apply_document_usage_filters",
    "filter_users_by_chw_ids",
    "focus_subtree_ids",
    "is_hierarchy_scoped_role",
    "org_user_index",
    "resolve_geography_chw_ids",
    "resolve_users_by_geography_ids",
    "resolve_users_by_geography_names",
    "resolve_visible_chw_ids",
    "user_display",
]
