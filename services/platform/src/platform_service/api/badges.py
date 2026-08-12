"""Badge catalog endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from mc_contracts.badges import (
    BadgeCreateRequest,
    BadgeListResponse,
    BadgeResponse,
    BadgeUpdateRequest,
)
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.auth.spice_user import get_selected_tenant_id, resolve_optional_spice_actor
from platform_service.db.repositories.badge_repository import (
    BADGE_SORT_DIRS,
    BADGE_SORT_KEYS,
    DEFAULT_BADGE_SORT_BY,
    DEFAULT_BADGE_SORT_DIR,
)
from platform_service.deps import get_db
from platform_service.services.badge_service import BadgeService

router = APIRouter(prefix="/admin", tags=["admin-badges"])


def _normalize_csv_query_values(raw: list[str] | None) -> list[str] | None:
    """Accept repeated params and/or comma-separated values; dedupe, preserve order."""
    if not raw:
        return None
    values: list[str] = []
    seen: set[str] = set()
    for item in raw:
        for part in item.split(","):
            value = part.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            values.append(value)
    return values or None


@router.post("/badges", response_model=BadgeResponse, status_code=201)
async def create_badge(
    request: Request,
    body: BadgeCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> BadgeResponse:
    tenant_id = get_selected_tenant_id(request)
    actor = resolve_optional_spice_actor(request)
    return await BadgeService(session).create(body, tenant_id=tenant_id, actor=actor)


@router.get("/badges", response_model=BadgeListResponse)
async def list_badges(
    domain: str | None = Query(None),
    created_by: list[str] | None = Query(
        None,
        description=(
            "Optional filter; exact match on badge.created_by. "
            "Repeat and/or comma-separate (e.g. created_by=alice&created_by=bob "
            "or created_by=alice,bob)."
        ),
    ),
    created_from: datetime | None = Query(
        None,
        description="Inclusive Created Date range start (badge.created_at).",
    ),
    created_to: datetime | None = Query(
        None,
        description="Inclusive Created Date range end (badge.created_at).",
    ),
    module_title: list[str] | None = Query(
        None,
        description=(
            "Optional filter; case-insensitive substring on linked module primary-locale title. "
            "Repeat and/or comma-separate; matches if badge links any matching module."
        ),
    ),
    q: str | None = Query(None, description="Case-insensitive substring match on badge name"),
    sort_by: str = Query(
        DEFAULT_BADGE_SORT_BY,
        description="created_at | sequence",
    ),
    sort_dir: str = Query(
        DEFAULT_BADGE_SORT_DIR,
        description="asc | desc",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> BadgeListResponse:
    if created_from is not None and created_to is not None and created_from > created_to:
        raise AppError(
            ErrorCode.INVALID_QUERY.value,
            "created_from must be on or before created_to",
            status=422,
        )
    if sort_by not in BADGE_SORT_KEYS:
        raise AppError(
            ErrorCode.INVALID_QUERY.value,
            f"sort_by must be one of: {', '.join(sorted(BADGE_SORT_KEYS))}",
            status=422,
        )
    if sort_dir not in BADGE_SORT_DIRS:
        raise AppError(
            ErrorCode.INVALID_QUERY.value,
            f"sort_dir must be one of: {', '.join(sorted(BADGE_SORT_DIRS))}",
            status=422,
        )
    return await BadgeService(session).list(
        domain=domain,
        created_by=_normalize_csv_query_values(created_by),
        created_from=created_from,
        created_to=created_to,
        module_titles=_normalize_csv_query_values(module_title),
        q=q,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get("/badges/{badge_id}", response_model=BadgeResponse)
async def get_badge(
    badge_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> BadgeResponse:
    return await BadgeService(session).get(badge_id)


@router.put("/badges/{badge_id}", response_model=BadgeResponse)
async def update_badge(
    request: Request,
    badge_id: UUID,
    body: BadgeUpdateRequest,
    session: AsyncSession = Depends(get_db),
) -> BadgeResponse:
    actor = resolve_optional_spice_actor(request)
    return await BadgeService(session).update(badge_id, body, actor=actor)


@router.delete("/badges/{badge_id}", status_code=204)
async def delete_badge(
    request: Request,
    badge_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> Response:
    actor = resolve_optional_spice_actor(request)
    await BadgeService(session).soft_delete(badge_id, actor=actor)
    return Response(status_code=204)
