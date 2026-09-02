"""Dashboard API — ClickHouse-backed analytics for administrators.

GET /dashboard/digital-help-modules      → DigitalHelpModuleUsageResponse
GET /dashboard/digital-help-modules/{module_id}/questions → DigitalHelpModuleQuestionsResponse
GET /dashboard/digital-help-modules/{module_id}/requests  → DigitalHelpModuleRequestsResponse
GET /dashboard/module-creation-suggestions → ModuleCreationSuggestionListResponse
GET /dashboard/module-creation-suggestions/{suggestion_id} → ModuleCreationSuggestionDetailResponse
GET /dashboard/module-demand-summary        → ModuleDemandSummaryResponse
GET /dashboard/team-activity             → TeamActivityResponse
GET /dashboard/team-activity/users/{user_id}/questions → TeamMemberQuestionsResponse
GET /dashboard/published-module-completions → PublishedModuleCompletionsResponse
GET /dashboard/document-usage            → DocumentUsageResponse

Digital-help and module-creation-suggestion reads are hierarchy-scoped:
AREA_MANAGER / PO see descendant demand only (not self); SHASTIYA_KORMI sees
self only; admins and auth-off remain unrestricted.

Those five digital-help / module-creation-suggestion routes also accept optional
``view=po|sk``. Omitted keeps all roles in scope. When set, SUPER_ADMIN and
AREA_MANAGER (Spice auth on) narrow ``chw_ids`` to PROGRAM_ORGANIZER (PO) or
SHASTIYA_KORMI actors; PO, SK, and auth-off ignore the param.

Team activity is one level at a time by default: members are the caller's
direct reports (Admin/auth-off → AMs; AM → POs; PO → SKs). Optional ``user_id``
focuses on a descendant and returns that user's children. Optional ``depth``
skips manager layers under the effective focus (Admin ``depth=1`` → POs,
``depth=2`` → SKs; AM ``depth=1`` → SKs). Member-questions uses the same
hierarchy scope (no ``po_user_id``). Published-module-completions is Admin /
Area Manager only (PO/SK → 403): modules with ``published_at`` in range,
excluding FAQ-only, with per-family SK completion counts in the same window
versus total descendant SKs. Document usage reads ``document_view_daily``
(KPIs / documents) and raw ``coaching_events`` (drill-down) in a single
response. Tenant comes from the authenticated request; optional ``user_id``
focuses hierarchy like team-activity (PO/AM role-aware subtree); viewer
scope is the authenticated principal (include-self).

Optional ``division_id``, ``district_id``, and ``upazila_id`` query params (integer
hierarchy ids; repeat and/or comma-separate for OR within each dimension; AND
across dimensions) narrow metrics to users in that geography on all routes below;
they compose with hierarchy scope and never widen visibility.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from mc_contracts.dashboard import (
    DigitalHelpModuleQuestionsResponse,
    DigitalHelpModuleRequestsResponse,
    DigitalHelpModuleUsageResponse,
    DocumentUsageResponse,
    ModuleCreationSuggestionDetailResponse,
    ModuleCreationSuggestionListResponse,
    ModuleDemandSummaryResponse,
    PublishedModuleCompletionsResponse,
    TeamActivityResponse,
    TeamMemberQuestionsResponse,
)
from mc_contracts.enums import DashboardActorView, HierarchyRole
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.api.query_params import normalize_int_csv_query_values
from platform_service.auth.spice_identity import (
    resolve_published_module_completions_scope,
    resolve_team_activity_scope,
)
from platform_service.auth.spice_user import get_selected_tenant_id, get_spice_user
from platform_service.config import get_settings
from platform_service.db.repositories.module_read_repository import (
    DEFAULT_MODULE_SORT_BY,
    DEFAULT_MODULE_SORT_DIR,
    MODULE_SORT_DIRS,
)
from platform_service.deps import get_clickhouse_client, get_db
from platform_service.services.dashboard_analytics_service import DashboardAnalyticsService
from platform_service.services.dashboard_hierarchy import (
    actor_view_role,
    apply_document_usage_filters,
    filter_chw_ids_by_role,
    is_hierarchy_scoped_role,
    org_user_index,
    resolve_users_by_geography_ids,
    resolve_visible_chw_ids,
)
from platform_service.services.document_usage_analytics_service import (
    DocumentUsageAnalyticsService,
    DocumentUsageFilter,
)
from platform_service.services.module_creation_suggestion_service import (
    ModuleCreationSuggestionService,
)
from platform_service.services.module_demand_summary_service import ModuleDemandSummaryService
from platform_service.services.published_module_completions_service import (
    PublishedModuleCompletionsService,
)
from platform_service.services.team_activity_service import (
    DEFAULT_TEAM_ACTIVITY_SORT_BY,
    DEFAULT_TEAM_ACTIVITY_SORT_DIR,
    TEAM_ACTIVITY_SORT_DIRS,
    TEAM_ACTIVITY_SORT_KEYS,
    TeamActivityService,
)

PUBLISHED_MODULE_COMPLETIONS_SORT_KEYS = frozenset({"published_at", "title"})

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
logger = logging.getLogger(__name__)

FromDate = Annotated[
    date,
    Query(alias="from", description="Inclusive start date (YYYY-MM-DD)."),
]
ToDate = Annotated[
    date,
    Query(alias="to", description="Inclusive end date (YYYY-MM-DD)."),
]
DivisionIdFilter = Annotated[
    list[str] | None,
    Query(
        description=(
            "Optional filter by user geography: division id(s); "
            "repeat and/or comma-separate (OR within; AND with district_id/upazila_id)"
        ),
    ),
]
DistrictIdFilter = Annotated[
    list[str] | None,
    Query(
        description=(
            "Optional filter by user geography: district id(s); "
            "repeat and/or comma-separate (OR within; AND with division_id/upazila_id)"
        ),
    ),
]
UpazilaIdFilter = Annotated[
    list[str] | None,
    Query(
        description=(
            "Optional filter by user geography: upazila id(s); "
            "repeat and/or comma-separate (OR within; AND with division_id/district_id)"
        ),
    ),
]
ActorViewFilter = Annotated[
    DashboardActorView | None,
    Query(
        description=(
            "Optional actor lens for digital-help and module-creation-suggestion routes: "
            "`po` (PROGRAM_ORGANIZER) or `sk` (SHASTIYA_KORMI). Omit for all roles. "
            "Honored only for SUPER_ADMIN and AREA_MANAGER when Spice auth is on; "
            "ignored for PO, SK, and auth-off."
        ),
    ),
]


def _parse_geography_id_filters(
    *,
    division_id: list[str] | None,
    district_id: list[str] | None,
    upazila_id: list[str] | None,
) -> tuple[list[int] | None, list[int] | None, list[int] | None]:
    """Normalize geography query params to integer id lists."""
    return (
        normalize_int_csv_query_values(division_id, param_name="division_id"),
        normalize_int_csv_query_values(district_id, param_name="district_id"),
        normalize_int_csv_query_values(upazila_id, param_name="upazila_id"),
    )


def _has_geography_filters(
    *,
    division_ids: list[int] | None,
    district_ids: list[int] | None,
    upazila_ids: list[int] | None,
) -> bool:
    return division_ids is not None or district_ids is not None or upazila_ids is not None


def _require_inclusive_date_range(*, from_date: date, to_date: date) -> None:
    if from_date > to_date:
        raise AppError(
            ErrorCode.VALIDATION_ERROR.value,
            "from_date must be on or before to_date",
            status=422,
        )


async def _dashboard_hierarchy_viewer(
    request: Request,
    session: AsyncSession,
    *,
    hierarchy_tenant_id: int,
) -> tuple[int | None, bool]:
    """Return (viewer_id, unrestricted). Auth-off and non-hierarchy admins are unrestricted."""
    settings = get_settings()
    if not settings.spice_auth_enabled:
        return None, True
    user = get_spice_user(request)
    viewer_id = user.id
    if viewer_id is None:
        return None, True
    org = (await org_user_index(session, tenant_id=hierarchy_tenant_id)).get(viewer_id)
    if org is not None and is_hierarchy_scoped_role(org.role):
        return viewer_id, False
    return viewer_id, True


async def _resolve_dashboard_chw_ids(
    request: Request,
    session: AsyncSession,
    *,
    include_self: bool,
    division_ids: list[int] | None = None,
    district_ids: list[int] | None = None,
    upazila_ids: list[int] | None = None,
) -> frozenset[int] | None:
    """Visible CHW set for hierarchy-scoped dashboard reads, or None if unrestricted."""
    hierarchy_tenant_id = get_selected_tenant_id(request)
    viewer_id, unrestricted = await _dashboard_hierarchy_viewer(
        request,
        session,
        hierarchy_tenant_id=hierarchy_tenant_id,
    )
    visible = await resolve_visible_chw_ids(
        session,
        viewer_id,
        tenant_id=hierarchy_tenant_id,
        unrestricted=unrestricted,
        include_self=include_self,
    )
    if not _has_geography_filters(
        division_ids=division_ids,
        district_ids=district_ids,
        upazila_ids=upazila_ids,
    ):
        return visible
    return await apply_document_usage_filters(
        session,
        visible,
        tenant_id=hierarchy_tenant_id,
        division_ids=division_ids,
        district_ids=district_ids,
        upazila_ids=upazila_ids,
    )


async def _apply_optional_actor_view(
    request: Request,
    session: AsyncSession,
    chw_ids: frozenset[int] | None,
    view: DashboardActorView | None,
) -> frozenset[int] | None:
    """Narrow ``chw_ids`` by ``view`` for eligible callers; otherwise return unchanged.

    Eligible: SUPER_ADMIN, AREA_MANAGER, or authenticated viewer not in the
    hierarchy map (platform admin). Auth-off, PO, and SK ignore ``view``.
    """
    if view is None:
        return chw_ids
    settings = get_settings()
    if not settings.spice_auth_enabled:
        return chw_ids

    tenant_id = get_selected_tenant_id(request)
    viewer_id, _unrestricted = await _dashboard_hierarchy_viewer(
        request,
        session,
        hierarchy_tenant_id=tenant_id,
    )
    if viewer_id is None:
        return chw_ids

    by_id = await org_user_index(session, tenant_id=tenant_id)
    viewer = by_id.get(viewer_id)
    if viewer is None:
        # Authenticated but not in hierarchy map — platform admin; honor view.
        eligible = True
    else:
        eligible = viewer.role in (
            HierarchyRole.SUPER_ADMIN.value,
            HierarchyRole.AREA_MANAGER.value,
        )
    if not eligible:
        return chw_ids

    return await filter_chw_ids_by_role(
        session,
        tenant_id=tenant_id,
        chw_ids=chw_ids,
        role=actor_view_role(view),
    )


async def _resolve_geography_ids_for_request(
    request: Request,
    session: AsyncSession,
    *,
    division_ids: list[int] | None,
    district_ids: list[int] | None,
    upazila_ids: list[int] | None,
) -> frozenset[int] | None:
    """Geography-only user filter for focus-based dashboard routes."""
    if not _has_geography_filters(
        division_ids=division_ids,
        district_ids=district_ids,
        upazila_ids=upazila_ids,
    ):
        return None
    tenant_id = get_selected_tenant_id(request)
    return await resolve_users_by_geography_ids(
        session,
        tenant_id=tenant_id,
        division_ids=division_ids,
        district_ids=district_ids,
        upazila_ids=upazila_ids,
    )


async def _build_document_usage_filter(
    request: Request,
    session: AsyncSession,
    *,
    from_date: date,
    to_date: date,
    division_ids: list[int] | None,
    district_ids: list[int] | None,
    upazila_ids: list[int] | None,
    user_id: int | None,
    document_id: UUID | None,
    title_query: str | None = None,
) -> DocumentUsageFilter:
    if from_date > to_date:
        raise AppError(
            ErrorCode.VALIDATION_ERROR.value,
            "'from' must be on or before 'to'.",
            status=422,
        )
    tenant_id = get_selected_tenant_id(request)
    viewer_id, unrestricted = await _dashboard_hierarchy_viewer(
        request,
        session,
        hierarchy_tenant_id=tenant_id,
    )
    return DocumentUsageFilter(
        from_date=from_date,
        to_date=to_date,
        tenant_id=tenant_id,
        division_ids=division_ids,
        district_ids=district_ids,
        upazila_ids=upazila_ids,
        user_id=user_id,
        document_id=document_id,
        title_query=title_query,
        viewer_id=viewer_id,
        unrestricted_viewer=unrestricted,
    )


@router.get("/digital-help-modules")
async def digital_help_module_usage(
    request: Request,
    from_date: date = Query(..., description="UTC start date (inclusive)."),
    to_date: date = Query(..., description="UTC end date (inclusive)."),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    division_id: DivisionIdFilter = None,
    district_id: DistrictIdFilter = None,
    upazila_id: UpazilaIdFilter = None,
    view: ActorViewFilter = None,
    session: AsyncSession = Depends(get_db),
) -> DigitalHelpModuleUsageResponse:
    """Rank modules by combined digital_help_used + module_requested volume (keyed on module_id)."""
    _require_inclusive_date_range(from_date=from_date, to_date=to_date)
    tenant_id = get_selected_tenant_id(request)
    division_ids, district_ids, upazila_ids = _parse_geography_id_filters(
        division_id=division_id,
        district_id=district_id,
        upazila_id=upazila_id,
    )
    chw_ids = await _resolve_dashboard_chw_ids(
        request,
        session,
        include_self=False,
        division_ids=division_ids,
        district_ids=district_ids,
        upazila_ids=upazila_ids,
    )
    chw_ids = await _apply_optional_actor_view(request, session, chw_ids, view)
    try:
        return await DashboardAnalyticsService(
            get_clickhouse_client(), session
        ).get_digital_help_module_usage(
            tenant_id=tenant_id,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
            chw_ids=chw_ids,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("ClickHouse query failed for digital help module usage")
        raise AppError(
            ErrorCode.ANALYTICS_UNAVAILABLE.value,
            "Analytics backend unavailable",
            status=502,
        ) from None


@router.get("/digital-help-modules/{module_id}/questions")
async def digital_help_module_questions(
    request: Request,
    module_id: UUID,
    from_date: date = Query(..., description="UTC start date (inclusive)."),
    to_date: date = Query(..., description="UTC end date (inclusive)."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    division_id: DivisionIdFilter = None,
    district_id: DistrictIdFilter = None,
    upazila_id: UpazilaIdFilter = None,
    view: ActorViewFilter = None,
    session: AsyncSession = Depends(get_db),
) -> DigitalHelpModuleQuestionsResponse:
    """Paginated chatbot questions for one module (keyed on module_id)."""
    _require_inclusive_date_range(from_date=from_date, to_date=to_date)
    tenant_id = get_selected_tenant_id(request)
    division_ids, district_ids, upazila_ids = _parse_geography_id_filters(
        division_id=division_id,
        district_id=district_id,
        upazila_id=upazila_id,
    )
    chw_ids = await _resolve_dashboard_chw_ids(
        request,
        session,
        include_self=False,
        division_ids=division_ids,
        district_ids=district_ids,
        upazila_ids=upazila_ids,
    )
    chw_ids = await _apply_optional_actor_view(request, session, chw_ids, view)
    try:
        return await DashboardAnalyticsService(
            get_clickhouse_client(), session
        ).get_digital_help_module_questions(
            module_id=module_id,
            tenant_id=tenant_id,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
            chw_ids=chw_ids,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("ClickHouse query failed for digital help module questions")
        raise AppError(
            ErrorCode.ANALYTICS_UNAVAILABLE.value,
            "Analytics backend unavailable",
            status=502,
        ) from None


@router.get("/digital-help-modules/{module_id}/requests")
async def digital_help_module_requests(
    request: Request,
    module_id: UUID,
    from_date: date = Query(..., description="UTC start date (inclusive)."),
    to_date: date = Query(..., description="UTC end date (inclusive)."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    division_id: DivisionIdFilter = None,
    district_id: DistrictIdFilter = None,
    upazila_id: UpazilaIdFilter = None,
    view: ActorViewFilter = None,
    session: AsyncSession = Depends(get_db),
) -> DigitalHelpModuleRequestsResponse:
    """Paginated module_requested events for one concrete module_id."""
    _require_inclusive_date_range(from_date=from_date, to_date=to_date)
    tenant_id = get_selected_tenant_id(request)
    division_ids, district_ids, upazila_ids = _parse_geography_id_filters(
        division_id=division_id,
        district_id=district_id,
        upazila_id=upazila_id,
    )
    chw_ids = await _resolve_dashboard_chw_ids(
        request,
        session,
        include_self=False,
        division_ids=division_ids,
        district_ids=district_ids,
        upazila_ids=upazila_ids,
    )
    chw_ids = await _apply_optional_actor_view(request, session, chw_ids, view)
    try:
        return await DashboardAnalyticsService(
            get_clickhouse_client(), session
        ).get_digital_help_module_requests(
            module_id=module_id,
            tenant_id=tenant_id,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
            chw_ids=chw_ids,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("ClickHouse query failed for digital help module requests")
        raise AppError(
            ErrorCode.ANALYTICS_UNAVAILABLE.value,
            "Analytics backend unavailable",
            status=502,
        ) from None


@router.get("/module-creation-suggestions")
async def list_module_creation_suggestions(
    request: Request,
    from_date: date = Query(..., description="UTC start date (inclusive)."),
    to_date: date = Query(..., description="UTC end date (inclusive)."),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    division_id: DivisionIdFilter = None,
    district_id: DistrictIdFilter = None,
    upazila_id: UpazilaIdFilter = None,
    view: ActorViewFilter = None,
    session: AsyncSession = Depends(get_db),
) -> ModuleCreationSuggestionListResponse:
    """List daily module-creation suggestions inferred from unattributed demand."""
    _require_inclusive_date_range(from_date=from_date, to_date=to_date)
    tenant_id = get_selected_tenant_id(request)
    division_ids, district_ids, upazila_ids = _parse_geography_id_filters(
        division_id=division_id,
        district_id=district_id,
        upazila_id=upazila_id,
    )
    chw_ids = await _resolve_dashboard_chw_ids(
        request,
        session,
        include_self=False,
        division_ids=division_ids,
        district_ids=district_ids,
        upazila_ids=upazila_ids,
    )
    chw_ids = await _apply_optional_actor_view(request, session, chw_ids, view)
    return await ModuleCreationSuggestionService(session).list_suggestions(
        tenant_id=tenant_id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
        visible_chw_ids=chw_ids,
    )


@router.get("/module-creation-suggestions/{suggestion_id}")
async def get_module_creation_suggestion(
    request: Request,
    suggestion_id: UUID,
    division_id: DivisionIdFilter = None,
    district_id: DistrictIdFilter = None,
    upazila_id: UpazilaIdFilter = None,
    view: ActorViewFilter = None,
    session: AsyncSession = Depends(get_db),
) -> ModuleCreationSuggestionDetailResponse:
    """Detail for one suggestion including chat questions and free-text requests."""
    tenant_id = get_selected_tenant_id(request)
    division_ids, district_ids, upazila_ids = _parse_geography_id_filters(
        division_id=division_id,
        district_id=district_id,
        upazila_id=upazila_id,
    )
    chw_ids = await _resolve_dashboard_chw_ids(
        request,
        session,
        include_self=False,
        division_ids=division_ids,
        district_ids=district_ids,
        upazila_ids=upazila_ids,
    )
    chw_ids = await _apply_optional_actor_view(request, session, chw_ids, view)
    try:
        return await ModuleCreationSuggestionService(session).get_detail(
            suggestion_id=suggestion_id,
            tenant_id=tenant_id,
            visible_chw_ids=chw_ids,
        )
    except LookupError as exc:
        raise AppError(ErrorCode.NOT_FOUND.value, str(exc), status=404) from exc


@router.get("/module-demand-summary")
async def module_demand_summary(
    request: Request,
    from_date: date = Query(..., description="UTC start date (inclusive)."),
    to_date: date = Query(..., description="UTC end date (inclusive)."),
    top_limit: int = Query(
        default=10,
        ge=1,
        le=50,
        description="Accepted for compatibility; scoring uses full-window category volumes.",
    ),
    division_id: DivisionIdFilter = None,
    district_id: DistrictIdFilter = None,
    upazila_id: UpazilaIdFilter = None,
    session: AsyncSession = Depends(get_db),
) -> ModuleDemandSummaryResponse:
    """Leverage-ordered structured summary of assign, publish, and create demand."""
    _require_inclusive_date_range(from_date=from_date, to_date=to_date)
    tenant_id = get_selected_tenant_id(request)
    division_ids, district_ids, upazila_ids = _parse_geography_id_filters(
        division_id=division_id,
        district_id=district_id,
        upazila_id=upazila_id,
    )
    chw_ids = await _resolve_dashboard_chw_ids(
        request,
        session,
        include_self=False,
        division_ids=division_ids,
        district_ids=district_ids,
        upazila_ids=upazila_ids,
    )
    try:
        return await ModuleDemandSummaryService(get_clickhouse_client(), session).get_summary(
            tenant_id=tenant_id,
            from_date=from_date,
            to_date=to_date,
            chw_ids=chw_ids,
            top_limit=top_limit,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Failed to build module demand summary")
        raise AppError(
            ErrorCode.ANALYTICS_UNAVAILABLE.value,
            "Analytics backend unavailable",
            status=502,
        ) from None


@router.get("/team-activity")
async def team_activity(
    request: Request,
    from_date: date = Query(..., description="UTC start date (inclusive)."),
    to_date: date = Query(..., description="UTC end date (inclusive)."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user_id: int | None = Query(
        default=None,
        description="Optional focus user in the caller's subtree; omit for caller default level.",
    ),
    depth: int = Query(
        default=0,
        ge=0,
        le=2,
        description=(
            "Member level under the effective focus: 0=direct children (default), "
            "1=skip one manager layer, 2=skip two (Admin→SKs). Illegal for the "
            "focus role → 422."
        ),
    ),
    sort_by: str = Query(
        default=DEFAULT_TEAM_ACTIVITY_SORT_BY,
        description="name | chatbot_engagement | module_completion | performance_status",
    ),
    sort_dir: str = Query(
        default=DEFAULT_TEAM_ACTIVITY_SORT_DIR,
        description="asc | desc",
    ),
    q: str | None = Query(
        default=None,
        description="Case-insensitive substring match on member name",
    ),
    division_id: DivisionIdFilter = None,
    district_id: DistrictIdFilter = None,
    upazila_id: UpazilaIdFilter = None,
    session: AsyncSession = Depends(get_db),
) -> TeamActivityResponse:
    """Hierarchy-scoped team activity with optional ``user_id`` and ``depth``."""

    # Validate date range; From Date must be on or before To Date
    _require_inclusive_date_range(from_date=from_date, to_date=to_date)

    if sort_by not in TEAM_ACTIVITY_SORT_KEYS:
        raise AppError(
            ErrorCode.INVALID_QUERY.value,
            f"sort_by must be one of: {', '.join(sorted(TEAM_ACTIVITY_SORT_KEYS))}",
            status=422,
        )
    if sort_dir not in TEAM_ACTIVITY_SORT_DIRS:
        raise AppError(
            ErrorCode.INVALID_QUERY.value,
            f"sort_dir must be one of: {', '.join(sorted(TEAM_ACTIVITY_SORT_DIRS))}",
            status=422,
        )

    tenant_id = get_selected_tenant_id(request)
    scope = await resolve_team_activity_scope(request, session, tenant_id=tenant_id)
    division_ids, district_ids, upazila_ids = _parse_geography_id_filters(
        division_id=division_id,
        district_id=district_id,
        upazila_id=upazila_id,
    )
    geo_chw_ids = await _resolve_geography_ids_for_request(
        request,
        session,
        division_ids=division_ids,
        district_ids=district_ids,
        upazila_ids=upazila_ids,
    )

    try:
        return await TeamActivityService(get_clickhouse_client(), session).get_team_activity(
            scope=scope,
            focus_user_id=user_id,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
            tenant_id=tenant_id,
            depth=depth,
            geo_chw_ids=geo_chw_ids,
            sort_by=sort_by,
            sort_dir=sort_dir,
            name_query=q.strip() if q and q.strip() else None,
        )
    except AppError:
        raise
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("ClickHouse query failed for team activity dashboard")
        raise AppError(
            ErrorCode.ANALYTICS_UNAVAILABLE.value,
            "Analytics backend unavailable",
            status=502,
        ) from None


@router.get("/team-activity/users/{user_id}/questions")
async def team_member_questions(
    request: Request,
    user_id: int,
    from_date: date = Query(..., description="UTC start date (inclusive)."),
    to_date: date = Query(..., description="UTC end date (inclusive)."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    division_id: DivisionIdFilter = None,
    district_id: DistrictIdFilter = None,
    upazila_id: UpazilaIdFilter = None,
    session: AsyncSession = Depends(get_db),
) -> TeamMemberQuestionsResponse:
    """Paginated chatbot questions for one hierarchy-visible team member."""
    _require_inclusive_date_range(from_date=from_date, to_date=to_date)

    tenant_id = get_selected_tenant_id(request)
    scope = await resolve_team_activity_scope(request, session, tenant_id=tenant_id)
    division_ids, district_ids, upazila_ids = _parse_geography_id_filters(
        division_id=division_id,
        district_id=district_id,
        upazila_id=upazila_id,
    )
    geo_chw_ids = await _resolve_geography_ids_for_request(
        request,
        session,
        division_ids=division_ids,
        district_ids=district_ids,
        upazila_ids=upazila_ids,
    )

    try:
        return await TeamActivityService(get_clickhouse_client(), session).get_member_questions(
            scope=scope,
            user_id=user_id,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
            tenant_id=tenant_id,
            geo_chw_ids=geo_chw_ids,
        )
    except AppError:
        raise
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("ClickHouse query failed for team member questions")
        raise AppError(
            ErrorCode.ANALYTICS_UNAVAILABLE.value,
            "Analytics backend unavailable",
            status=502,
        ) from None


@router.get("/published-module-completions")
async def published_module_completions(
    request: Request,
    from_date: date = Query(..., description="UTC start date (inclusive)."),
    to_date: date = Query(..., description="UTC end date (inclusive)."),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    module_id: list[UUID] | None = Query(
        default=None,
        description="Optional module id filter; repeat for multi-select (OR).",
    ),
    sort_by: str = Query(
        default=DEFAULT_MODULE_SORT_BY,
        description="published_at | title",
    ),
    sort_dir: str = Query(
        default=DEFAULT_MODULE_SORT_DIR,
        description="asc | desc",
    ),
    division_id: DivisionIdFilter = None,
    district_id: DistrictIdFilter = None,
    upazila_id: UpazilaIdFilter = None,
    session: AsyncSession = Depends(get_db),
) -> PublishedModuleCompletionsResponse:
    """Modules published in range with Admin/AM descendant SK completion counts.

    Completions are counted per ``module_family_id``. Multiple published versions
    of the same family in the window each appear as a row but share
    ``completed_sk_count``. FAQ-only modules are excluded. Only currently
    ``published`` rows are listed.
    """
    _require_inclusive_date_range(from_date=from_date, to_date=to_date)

    if sort_by not in PUBLISHED_MODULE_COMPLETIONS_SORT_KEYS:
        raise AppError(
            ErrorCode.INVALID_QUERY.value,
            f"sort_by must be one of: {', '.join(sorted(PUBLISHED_MODULE_COMPLETIONS_SORT_KEYS))}",
            status=422,
        )
    if sort_dir not in MODULE_SORT_DIRS:
        raise AppError(
            ErrorCode.INVALID_QUERY.value,
            f"sort_dir must be one of: {', '.join(sorted(MODULE_SORT_DIRS))}",
            status=422,
        )

    tenant_id = get_selected_tenant_id(request)
    scope = await resolve_published_module_completions_scope(request, session, tenant_id=tenant_id)
    division_ids, district_ids, upazila_ids = _parse_geography_id_filters(
        division_id=division_id,
        district_id=district_id,
        upazila_id=upazila_id,
    )
    geo_chw_ids = await _resolve_geography_ids_for_request(
        request,
        session,
        division_ids=division_ids,
        district_ids=district_ids,
        upazila_ids=upazila_ids,
    )
    return await PublishedModuleCompletionsService(session).get_published_module_completions(
        scope=scope,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
        tenant_id=tenant_id,
        geo_chw_ids=geo_chw_ids,
        module_ids=module_id,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@router.get("/document-usage")
async def document_usage(
    request: Request,
    from_date: FromDate,
    to_date: ToDate,
    division_id: DivisionIdFilter = None,
    district_id: DistrictIdFilter = None,
    upazila_id: UpazilaIdFilter = None,
    user_id: int | None = Query(
        default=None,
        description=(
            "Optional focus user in the caller's subtree (like team-activity). "
            "PO → that PO + child SKs; AM → AM + descendants; SK → that user. "
            "Omit for the authenticated viewer's default scope."
        ),
    ),
    document_id: UUID | None = Query(default=None),
    q: str | None = Query(
        default=None,
        description=(
            "Optional case-insensitive substring on document title. "
            "Omit or whitespace → no title filter. Narrows documents[] and "
            "total_document_rows only (KPIs, top_documents, and events are unchanged)."
        ),
    ),
    top_limit: int = Query(default=10, ge=1, le=50),
    documents_limit: int = Query(default=20, ge=1, le=100),
    documents_offset: int = Query(default=0, ge=0),
    events_limit: int = Query(default=50, ge=1, le=200),
    events_offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> DocumentUsageResponse:
    """Document-view KPIs, per-document table, and event drill-down in one response."""
    parsed_division_ids, parsed_district_ids, parsed_upazila_ids = _parse_geography_id_filters(
        division_id=division_id,
        district_id=district_id,
        upazila_id=upazila_id,
    )
    filters = await _build_document_usage_filter(
        request,
        session,
        from_date=from_date,
        to_date=to_date,
        division_ids=parsed_division_ids,
        district_ids=parsed_district_ids,
        upazila_ids=parsed_upazila_ids,
        user_id=user_id,
        document_id=document_id,
        title_query=q.strip() if q and q.strip() else None,
    )
    try:
        return await DocumentUsageAnalyticsService(get_clickhouse_client(), session).get_usage(
            filters,
            top_limit=top_limit,
            documents_limit=documents_limit,
            documents_offset=documents_offset,
            events_limit=events_limit,
            events_offset=events_offset,
        )
    except AppError:
        raise
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("ClickHouse query failed for document usage")
        raise AppError(
            ErrorCode.ANALYTICS_UNAVAILABLE.value,
            "Analytics backend unavailable",
            status=502,
        ) from None
