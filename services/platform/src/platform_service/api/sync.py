"""Scenario and config sync endpoints — platform → Android SDK.

Canonical paths:
  GET /scenarios/sync?since_version=N → ScenarioSyncBundle
  GET /config/sync                    → ConfigSyncBundle
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from mc_contracts.sync import ConfigSyncBundle, GapsSyncBundle, ModulesSyncBundle, TriggersSyncBundle
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.deps import get_db
from platform_service.services.sync_service import SyncService

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/config", response_model=ConfigSyncBundle)
async def sync_config(
    db: AsyncSession = Depends(get_db),
) -> ConfigSyncBundle:
    """Return current config threshold snapshot for offline device use."""
    return await SyncService(db).get_config_bundle()


@router.get("/modules", response_model=ModulesSyncBundle)
async def sync_modules(
    since: datetime = Query(
        ..., description="ISO-8601 datetime; return modules updated after this timestamp"
    ),
    db: AsyncSession = Depends(get_db),
) -> ModulesSyncBundle:
    """Return published modules updated after `since` (plus their quiz payloads)."""
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    return await SyncService(db).get_modules_bundle(since=since)


@router.get("/triggers", response_model=TriggersSyncBundle)
async def sync_triggers(
    since: datetime = Query(
        ...,
        description="ISO-8601 datetime; return triggers updated after this timestamp (and all bindings for them)",
    ),
    db: AsyncSession = Depends(get_db),
) -> TriggersSyncBundle:
    """Return trigger definitions updated after `since` plus their module-family bindings."""
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    return await SyncService(db).get_triggers_bundle(since=since)


@router.get("/gaps", response_model=GapsSyncBundle)
async def sync_gaps(
    since: datetime | None = Query(
        default=None,
        description="ISO-8601 datetime; return gaps/state rows updated after this timestamp",
    ),
    chw_id: int | None = Query(
        default=None,
        description="Optional CHW id (integer). When provided, include per-CHW gap state and module completion state.",
    ),
    db: AsyncSession = Depends(get_db),
) -> GapsSyncBundle:
    """Return behavioural gaps plus optional per-CHW state for offline sync."""
    if since is not None and since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    return await SyncService(db).get_gaps_bundle(since=since, chw_id=chw_id)
