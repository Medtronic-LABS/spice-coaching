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

Optional ``division``, ``district``, and ``upazila_id`` query params (org-map name strings,
case-insensitive) narrow metrics to users in that geography on all routes below;
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
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.auth.spice_identity import (
    resolve_published_module_completions_scope,
    resolve_team_activity_scope,
)
from platform_service.auth.spice_user import get_selected_tenant_id, get_spice_user
from platform_service.config import get_settings
from platform_service.deps import get_clickhouse_client, get_db
from platform_service.services.dashboard_analytics_service import DashboardAnalyticsService
from platform_service.services.dashboard_hierarchy import (
    apply_document_usage_filters,
    is_hierarchy_scoped_role,
    org_user_index,
    resolve_geography_chw_ids,
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
from platform_service.services.team_activity_service import TeamActivityService

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
DivisionFilter = Annotated[
    str | None,
    Query(description="Filter metrics to users in this division (org-map name)."),
]
DistrictFilter = Annotated[
    str | None,
    Query(description="Filter metrics to users in this district (org-map name)."),
]
UpazilaFilter = Annotated[
    str | None,
    Query(
        alias="upazila_id",
        description="Filter metrics to users in this upazila (org-map name; same semantics as district).",
    ),
]


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
    division: str | None = None,
    district: str | None = None,
    upazila_id: str | None = None,
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
    if not division and not district and not upazila_id:
        return visible
    return await apply_document_usage_filters(
        session,
        visible,
        tenant_id=hierarchy_tenant_id,
        division=division.strip() if division else None,
        district=district.strip() if district else None,
        upazila=upazila_id.strip() if upazila_id else None,
    )


async def _resolve_geography_chw_ids_for_request(
    request: Request,
    session: AsyncSession,
    *,
    division: str | None,
    district: str | None,
    upazila_id: str | None,
) -> frozenset[int] | None:
    """Geography-only user filter for focus-based dashboard routes."""
    if not division and not district and not upazila_id:
        return None
    tenant_id = get_selected_tenant_id(request)
    return await resolve_geography_chw_ids(
        session,
        tenant_id=tenant_id,
        division=division.strip() if division else None,
        district=district.strip() if district else None,
        upazila=upazila_id.strip() if upazila_id else None,
    )


async def _build_document_usage_filter(
    request: Request,
    session: AsyncSession,
    *,
    from_date: date,
    to_date: date,
    upazila_id: str | None,
    division: str | None,
    district: str | None,
    user_id: int | None,
    document_id: UUID | None,
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
        upazila=upazila_id.strip() if upazila_id else None,
        division=division.strip() if division else None,
        district=district.strip() if district else None,
        user_id=user_id,
        document_id=document_id,
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
    division: DivisionFilter = None,
    district: DistrictFilter = None,
    upazila_id: UpazilaFilter = None,
    session: AsyncSession = Depends(get_db),
) -> DigitalHelpModuleUsageResponse:
    """Rank modules by combined digital_help_used + module_requested volume (keyed on module_id)."""
    _require_inclusive_date_range(from_date=from_date, to_date=to_date)
    tenant_id = get_selected_tenant_id(request)
    chw_ids = await _resolve_dashboard_chw_ids(
        request,
        session,
        include_self=False,
        division=division,
        district=district,
        upazila_id=upazila_id,
    )
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
    division: DivisionFilter = None,
    district: DistrictFilter = None,
    upazila_id: UpazilaFilter = None,
    session: AsyncSession = Depends(get_db),
) -> DigitalHelpModuleQuestionsResponse:
    """Paginated chatbot questions for one module (keyed on module_id)."""
    _require_inclusive_date_range(from_date=from_date, to_date=to_date)
    tenant_id = get_selected_tenant_id(request)
    chw_ids = await _resolve_dashboard_chw_ids(
        request,
        session,
        include_self=False,
        division=division,
        district=district,
        upazila_id=upazila_id,
    )
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
    division: DivisionFilter = None,
    district: DistrictFilter = None,
    upazila_id: UpazilaFilter = None,
    session: AsyncSession = Depends(get_db),
) -> DigitalHelpModuleRequestsResponse:
    """Paginated module_requested events for one concrete module_id."""
    _require_inclusive_date_range(from_date=from_date, to_date=to_date)
    tenant_id = get_selected_tenant_id(request)
    chw_ids = await _resolve_dashboard_chw_ids(
        request,
        session,
        include_self=False,
        division=division,
        district=district,
        upazila_id=upazila_id,
    )
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
    division: DivisionFilter = None,
    district: DistrictFilter = None,
    upazila_id: UpazilaFilter = None,
    session: AsyncSession = Depends(get_db),
) -> ModuleCreationSuggestionListResponse:
    """List daily module-creation suggestions inferred from unattributed demand."""
    _require_inclusive_date_range(from_date=from_date, to_date=to_date)
    tenant_id = get_selected_tenant_id(request)
    chw_ids = await _resolve_dashboard_chw_ids(
        request,
        session,
        include_self=False,
        division=division,
        district=district,
        upazila_id=upazila_id,
    )
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
    division: DivisionFilter = None,
    district: DistrictFilter = None,
    upazila_id: UpazilaFilter = None,
    session: AsyncSession = Depends(get_db),
) -> ModuleCreationSuggestionDetailResponse:
    """Detail for one suggestion including chat questions and free-text requests."""
    tenant_id = get_selected_tenant_id(request)
    chw_ids = await _resolve_dashboard_chw_ids(
        request,
        session,
        include_self=False,
        division=division,
        district=district,
        upazila_id=upazila_id,
    )
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
    top_limit: int = Query(default=10, ge=1, le=50),
    division: DivisionFilter = None,
    district: DistrictFilter = None,
    upazila_id: UpazilaFilter = None,
    session: AsyncSession = Depends(get_db),
) -> ModuleDemandSummaryResponse:
    """Text summary of attributed module usage and inferred modules to add."""
    _require_inclusive_date_range(from_date=from_date, to_date=to_date)
    tenant_id = get_selected_tenant_id(request)
    chw_ids = await _resolve_dashboard_chw_ids(
        request,
        session,
        include_self=False,
        division=division,
        district=district,
        upazila_id=upazila_id,
    )
    try:
        return await ModuleDemandSummaryService(get_clickhouse_client(), session).get_text_summary(
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
    division: DivisionFilter = None,
    district: DistrictFilter = None,
    upazila_id: UpazilaFilter = None,
    session: AsyncSession = Depends(get_db),
) -> TeamActivityResponse:
    """Hierarchy-scoped team activity with optional ``user_id`` and ``depth``."""

    # Validate date range; From Date must be on or before To Date
    _require_inclusive_date_range(from_date=from_date, to_date=to_date)

    tenant_id = get_selected_tenant_id(request)
    scope = await resolve_team_activity_scope(request, session, tenant_id=tenant_id)
    geo_chw_ids = await _resolve_geography_chw_ids_for_request(
        request,
        session,
        division=division,
        district=district,
        upazila_id=upazila_id,
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
    division: DivisionFilter = None,
    district: DistrictFilter = None,
    upazila_id: UpazilaFilter = None,
    session: AsyncSession = Depends(get_db),
) -> TeamMemberQuestionsResponse:
    """Paginated chatbot questions for one hierarchy-visible team member."""
    _require_inclusive_date_range(from_date=from_date, to_date=to_date)

    tenant_id = get_selected_tenant_id(request)
    scope = await resolve_team_activity_scope(request, session, tenant_id=tenant_id)
    geo_chw_ids = await _resolve_geography_chw_ids_for_request(
        request,
        session,
        division=division,
        district=district,
        upazila_id=upazila_id,
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
    division: DivisionFilter = None,
    district: DistrictFilter = None,
    upazila_id: UpazilaFilter = None,
    session: AsyncSession = Depends(get_db),
) -> PublishedModuleCompletionsResponse:
    """Modules published in range with Admin/AM descendant SK completion counts.

    Completions are counted per ``module_family_id``. Multiple published versions
    of the same family in the window each appear as a row but share
    ``completed_sk_count``. FAQ-only modules are excluded. Only currently
    ``published`` rows are listed.
    """
    _require_inclusive_date_range(from_date=from_date, to_date=to_date)

    tenant_id = get_selected_tenant_id(request)
    scope = await resolve_published_module_completions_scope(request, session, tenant_id=tenant_id)
    geo_chw_ids = await _resolve_geography_chw_ids_for_request(
        request,
        session,
        division=division,
        district=district,
        upazila_id=upazila_id,
    )
    return await PublishedModuleCompletionsService(session).get_published_module_completions(
        scope=scope,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
        tenant_id=tenant_id,
        geo_chw_ids=geo_chw_ids,
    )


@router.get("/document-usage")
async def document_usage(
    request: Request,
    from_date: FromDate,
    to_date: ToDate,
    upazila_id: str | None = Query(
        default=None,
        description="Filter by org-map upazila (same semantics as district).",
    ),
    division: str | None = Query(default=None, description="Filter by org-map division (name string)."),
    district: str | None = Query(default=None),
    user_id: int | None = Query(
        default=None,
        description=(
            "Optional focus user in the caller's subtree (like team-activity). "
            "PO → that PO + child SKs; AM → AM + descendants; SK → that user. "
            "Omit for the authenticated viewer's default scope."
        ),
    ),
    document_id: UUID | None = Query(default=None),
    top_limit: int = Query(default=10, ge=1, le=50),
    documents_limit: int = Query(default=20, ge=1, le=100),
    documents_offset: int = Query(default=0, ge=0),
    events_limit: int = Query(default=50, ge=1, le=200),
    events_offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> DocumentUsageResponse:
    """Document-view KPIs, per-document table, and event drill-down in one response."""
    filters = await _build_document_usage_filter(
        request,
        session,
        from_date=from_date,
        to_date=to_date,
        upazila_id=upazila_id,
        division=division,
        district=district,
        user_id=user_id,
        document_id=document_id,
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
