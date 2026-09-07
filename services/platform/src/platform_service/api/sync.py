"""Scenario and config sync endpoints — platform → Android SDK.

Canonical paths:
  GET /scenarios/sync?since_version=N → ScenarioSyncBundle
  GET /sync/config                    → ConfigSyncBundle
  GET  /sync/source-documents?since=<ISO-8601> → SourceDocumentsSyncBundle
  GET  /sync/chat-faqs?since=<ISO-8601> → ChatFaqsSyncBundle
  GET  /sync/card-embeddings?since=<ISO-8601> → CardEmbeddingsSyncBundle
  GET  /sync/badges                       → BadgesSyncBundle
  GET  /sync/video-progress?since=<ISO-8601> → VideoProgressSyncBundle
  POST /sync/presigned-urls               → StoragePathsPresignResponse (object names)
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from mc_contracts.sync import (
    BadgesSyncBundle,
    CardEmbeddingsSyncBundle,
    ChatFaqsSyncBundle,
    ConfigSyncBundle,
    GapsSyncBundle,
    ModulesSyncBundle,
    SourceDocumentsSyncBundle,
    StoragePathsPresignRequest,
    StoragePathsPresignResponse,
    TriggersSyncBundle,
    VideoProgressSyncBundle,
)
from mc_foundation.objectstore import ObjectStore
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.auth.spice_identity import resolve_sync_user_id
from platform_service.auth.spice_user import get_selected_tenant_id
from platform_service.config import Settings, get_settings
from platform_service.deps import get_db, get_object_storage_client
from platform_service.services.sync_service import SyncService

router = APIRouter(prefix="/sync", tags=["sync"])


def _effective_tenant_id(request: Request) -> int:
    return get_selected_tenant_id(request)


@router.get("/source-documents", response_model=SourceDocumentsSyncBundle)
async def sync_source_documents(
    request: Request,
    since: datetime = Query(
        ...,
        description="ISO-8601 datetime; return module-linked documents updated after this timestamp",
    ),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStore = Depends(get_object_storage_client),
    settings: Settings = Depends(get_settings),
) -> SourceDocumentsSyncBundle:
    """Return presigned URLs for module-linked and assigned source documents.

    ``source_documents`` covers docs linked to all currently published modules in the
    tenant with ``updated_at > since`` (retired excluded). ``assigned_documents`` is
    the authenticated user's full current ``document_assignment`` snapshot (ignores
    ``since``), also excluding retired.
    """
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)

    effective_tenant = _effective_tenant_id(request)
    effective_user_id = resolve_sync_user_id(request)

    return await SyncService(db).get_source_documents_bundle(
        since=since,
        storage=storage,
        tenant_id=effective_tenant,
        user_id=effective_user_id,
        settings=settings,
    )


@router.get("/config", response_model=ConfigSyncBundle)
async def sync_config(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ConfigSyncBundle:
    """Return current config threshold snapshot for offline device use."""
    return await SyncService(db).get_config_bundle(tenant_id=_effective_tenant_id(request))


@router.get("/modules", response_model=ModulesSyncBundle)
async def sync_modules(
    request: Request,
    since: datetime = Query(
        ..., description="ISO-8601 datetime; return modules updated after this timestamp"
    ),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStore = Depends(get_object_storage_client),
    settings: Settings = Depends(get_settings),
) -> ModulesSyncBundle:
    """Return published modules updated after `since` (plus their quiz payloads).

    Also returns ``assigned_module_ids`` and the CHW's full ``requested_modules`` history
    for the authenticated user. Module thumbnails are inline-presigned when available.
    """
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)

    effective_tenant = _effective_tenant_id(request)
    effective_user_id = resolve_sync_user_id(request)

    return await SyncService(db).get_modules_bundle(
        since=since,
        tenant_id=effective_tenant,
        user_id=effective_user_id,
        storage=storage,
        settings=settings,
    )


@router.get("/card-embeddings", response_model=CardEmbeddingsSyncBundle)
async def sync_card_embeddings(
    request: Request,
    since: datetime = Query(
        ...,
        description="ISO-8601 datetime; return embeddings for published modules updated after this timestamp",
    ),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CardEmbeddingsSyncBundle:
    """Return card embedding vectors for published training modules updated after ``since``.

    Cards without a persisted ``local_embedding`` are omitted. Join on ``card_id`` with
    the card payloads from ``GET /sync/modules``.
    """
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)

    resolve_sync_user_id(request)
    effective_tenant = _effective_tenant_id(request)

    return await SyncService(db).get_card_embeddings_bundle(
        since=since,
        tenant_id=effective_tenant,
        settings=settings,
    )


@router.get("/triggers", response_model=TriggersSyncBundle)
async def sync_triggers(
    request: Request,
    since: datetime = Query(
        ...,
        description="ISO-8601 datetime; return triggers updated after this timestamp (and all bindings for them)",
    ),
    db: AsyncSession = Depends(get_db),
) -> TriggersSyncBundle:
    """Return trigger definitions updated after `since` plus their module-family bindings."""
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    effective_tenant = _effective_tenant_id(request)
    return await SyncService(db).get_triggers_bundle(since=since, tenant_id=effective_tenant)


@router.get("/gaps", response_model=GapsSyncBundle)
async def sync_gaps(
    request: Request,
    since: datetime | None = Query(
        default=None,
        description="ISO-8601 datetime; return gaps/state rows updated after this timestamp",
    ),
    db: AsyncSession = Depends(get_db),
) -> GapsSyncBundle:
    """Return behavioural gaps plus per-CHW state and partial quiz progress for offline sync."""
    if since is not None and since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    effective_chw_id = resolve_sync_user_id(request)
    effective_tenant = _effective_tenant_id(request)
    return await SyncService(db).get_gaps_bundle(
        since=since,
        chw_id=effective_chw_id,
        tenant_id=effective_tenant,
    )


@router.get("/chat-faqs", response_model=ChatFaqsSyncBundle)
async def sync_chat_faqs(
    request: Request,
    since: datetime = Query(..., description="ISO-8601 datetime; return FAQs updated after this timestamp"),
    db: AsyncSession = Depends(get_db),
) -> ChatFaqsSyncBundle:
    """Return ranked frequent chat questions, optionally scoped to a tenant."""
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    effective_tenant = _effective_tenant_id(request)
    return await SyncService(db).get_chat_faqs_bundle(since=since, tenant_id=effective_tenant)


@router.get("/badges", response_model=BadgesSyncBundle)
async def sync_badges(
    request: Request,
    db: AsyncSession = Depends(get_db),
    storage: ObjectStore = Depends(get_object_storage_client),
    settings: Settings = Depends(get_settings),
) -> BadgesSyncBundle:
    """Return available active tenant badges and earned badges for the authenticated CHW."""
    effective_user_id = resolve_sync_user_id(request)
    tenant_id = _effective_tenant_id(request)
    return await SyncService(db).get_badges_bundle(
        user_id=effective_user_id,
        tenant_id=tenant_id,
        storage=storage,
        settings=settings,
    )


@router.get("/video-progress", response_model=VideoProgressSyncBundle)
async def sync_video_progress(
    request: Request,
    since: datetime = Query(
        ...,
        description="ISO-8601 datetime; return assigned-video progress updated after this timestamp",
    ),
    db: AsyncSession = Depends(get_db),
) -> VideoProgressSyncBundle:
    """Return delta watch progress for videos still assigned to the authenticated CHW.

    Only ``source_type=video`` documents with a current ``document_assignment`` and an
    existing ``chw_video_progress`` row with ``updated_at > since`` are included.
    Unwatched assigned videos (no progress row) are omitted. Writes remain on
    ``POST /telemetry/events`` (``video_progress_updated``).
    """
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)

    effective_tenant = _effective_tenant_id(request)
    effective_user_id = resolve_sync_user_id(request)

    return await SyncService(db).get_video_progress_bundle(
        since=since,
        user_id=effective_user_id,
        tenant_id=effective_tenant,
    )


@router.post("/presigned-urls", response_model=StoragePathsPresignResponse)
async def sync_presigned_urls(
    body: StoragePathsPresignRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    storage: ObjectStore = Depends(get_object_storage_client),
    settings: Settings = Depends(get_settings),
) -> StoragePathsPresignResponse:
    """Return presigned GET URLs for a batch of object names (partial success).

    Accepts object names only (same normalisation as ``GET /admin/files/presigned-url``).
    Full ``bucket/key`` refs and filesystem paths are listed in ``missing_paths``.
    """
    resolve_sync_user_id(request)
    return await SyncService(db).get_presigned_urls_for_storage_paths(
        storage_paths=body.storage_paths,
        storage=storage,
        settings=settings,
    )
