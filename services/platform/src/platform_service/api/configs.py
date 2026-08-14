from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from mc_contracts.configs import (
    ConfigThresholdChangeItem,
    ConfigThresholdChangeListResponse,
    ConfigThresholdResponse,
    ConfigThresholdUpdateRequest,
)
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.auth.spice_user import get_selected_tenant_id, resolve_spice_actor
from platform_service.db.repositories.config_threshold_repository import ConfigThresholdRepository
from platform_service.deps import get_db

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])


@router.get("/configs", response_model=list[ConfigThresholdResponse])
async def list_configs(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> list[ConfigThresholdResponse]:
    """Retrieve all configuration thresholds."""
    repo = ConfigThresholdRepository(session)
    configs = await repo.list_all(tenant_id=get_selected_tenant_id(request))
    return [ConfigThresholdResponse.model_validate(c) for c in configs]


@router.get("/configs/{key}", response_model=ConfigThresholdResponse)
async def get_config(
    key: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ConfigThresholdResponse:
    """Retrieve a single configuration threshold by key."""
    repo = ConfigThresholdRepository(session)
    config = await repo.get_by_key(key, tenant_id=get_selected_tenant_id(request))
    if config is None:
        raise AppError(
            ErrorCode.CONFIG_NOT_FOUND.value,
            f"Config threshold with key '{key}' not found.",
            status=404,
        )
    return ConfigThresholdResponse.model_validate(config)


@router.get("/configs/{key}/changes", response_model=ConfigThresholdChangeListResponse)
async def list_config_changes(
    key: str,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> ConfigThresholdChangeListResponse:
    """Retrieve paginated change history for a configuration key."""
    tenant_id = get_selected_tenant_id(request)
    repo = ConfigThresholdRepository(session)
    metadata = await repo.get_metadata_by_key(key, tenant_id=tenant_id)
    if metadata is None:
        raise AppError(
            ErrorCode.CONFIG_NOT_FOUND.value,
            f"Config threshold with key '{key}' not found.",
            status=404,
        )

    changes, total_changes = await repo.list_changes(
        key,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
    )
    total_pages = (total_changes + limit - 1) // limit if total_changes > 0 else 0
    return ConfigThresholdChangeListResponse(
        changes=[ConfigThresholdChangeItem.model_validate(c) for c in changes],
        total_changes=total_changes,
        total_pages=total_pages,
        limit=limit,
        offset=offset,
    )


@router.put("/configs/{key}", response_model=ConfigThresholdResponse)
async def update_config(
    key: str,
    body: ConfigThresholdUpdateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ConfigThresholdResponse:
    """Update an existing configuration threshold."""
    repo = ConfigThresholdRepository(session)
    updated = await repo.update_config(
        key,
        body.value_json,
        tenant_id=get_selected_tenant_id(request),
        updated_by=resolve_spice_actor(request),
        title=body.title,
        description=body.description,
    )
    if updated is None:
        raise AppError(
            ErrorCode.CONFIG_NOT_FOUND.value,
            f"Config threshold with key '{key}' not found.",
            status=404,
        )

    await session.commit()
    return ConfigThresholdResponse.model_validate(updated)
