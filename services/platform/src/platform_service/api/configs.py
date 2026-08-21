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

from platform_service.auth.spice_user import get_selected_tenant_id, resolve_spice_user_id
from platform_service.db.repositories.config_threshold_repository import (
    ConfigThresholdChangeRecord,
    ConfigThresholdRepository,
    ConfigThresholdState,
)
from platform_service.db.repositories.hierarchy_repository import HierarchyRepository
from platform_service.deps import get_db
from platform_service.services.user_actor_ref import to_user_actor_ref

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])


async def _resolve_actor_map(
    session: AsyncSession,
    *user_ids: int | None,
) -> dict:
    ids = [uid for uid in user_ids if uid is not None]
    if not ids:
        return {}
    return await HierarchyRepository(session).get_users_by_ids(ids)


def _config_response(state: ConfigThresholdState, users_by_id: dict) -> ConfigThresholdResponse:
    return ConfigThresholdResponse(
        id=state.id,
        version=state.version,
        key=state.key,
        value_json=state.value_json,
        title=state.title,
        description=state.description,
        created_at=state.created_at,
        updated_at=state.updated_at,
        updated_by=to_user_actor_ref(state.updated_by, users_by_id),
    )


def _change_item(record: ConfigThresholdChangeRecord, users_by_id: dict) -> ConfigThresholdChangeItem:
    return ConfigThresholdChangeItem(
        previous_value_json=record.previous_value_json,
        current_value_json=record.current_value_json,
        updated_by=to_user_actor_ref(record.updated_by, users_by_id),
        updated_at=record.updated_at,
    )


@router.get("/configs", response_model=list[ConfigThresholdResponse])
async def list_configs(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> list[ConfigThresholdResponse]:
    """Retrieve all configuration thresholds."""
    repo = ConfigThresholdRepository(session)
    configs = await repo.list_all(tenant_id=get_selected_tenant_id(request))
    users_by_id = await _resolve_actor_map(session, *(c.updated_by for c in configs))
    return [_config_response(c, users_by_id) for c in configs]


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
    users_by_id = await _resolve_actor_map(session, config.updated_by)
    return _config_response(config, users_by_id)


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
    users_by_id = await _resolve_actor_map(session, *(c.updated_by for c in changes))
    total_pages = (total_changes + limit - 1) // limit if total_changes > 0 else 0
    return ConfigThresholdChangeListResponse(
        changes=[_change_item(c, users_by_id) for c in changes],
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
        updated_by=resolve_spice_user_id(request),
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
    users_by_id = await _resolve_actor_map(session, updated.updated_by)
    return _config_response(updated, users_by_id)
