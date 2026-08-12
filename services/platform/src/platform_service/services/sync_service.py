"""Scenario sync service — builds ScenarioSyncBundle for device sync endpoint.

Devices (Android SDK) call /scenarios/sync?since_version=N to pull:
  - validated scenarios with version > N (excluding soft-deleted)
  - tombstone lists for removed scenarios / quizzes
  - associated validated quiz questions
  - ``current_version`` watermark for the next sync cursor
"""

from __future__ import annotations

from datetime import datetime

from mc_contracts.sync import (
    BadgesSyncBundle,
    ChatFaqsSyncBundle,
    ConfigSyncBundle,
    GapsSyncBundle,
    ModulesSyncBundle,
    SourceDocumentsSyncBundle,
    TriggersSyncBundle,
    VideoProgressSyncBundle,
)
from mc_foundation.objectstore import ObjectStore
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.config import Settings
from platform_service.services.sync.badges_bundle_builder import BadgesBundleBuilder
from platform_service.services.sync.chat_faqs_bundle_builder import ChatFaqsBundleBuilder
from platform_service.services.sync.config_bundle_builder import ConfigBundleBuilder
from platform_service.services.sync.gaps_bundle_builder import GapsBundleBuilder
from platform_service.services.sync.modules_bundle_builder import ModulesBundleBuilder
from platform_service.services.sync.source_documents_bundle_builder import (
    SourceDocumentsBundleBuilder,
)
from platform_service.services.sync.triggers_bundle_builder import TriggersBundleBuilder
from platform_service.services.sync.video_progress_bundle_builder import VideoProgressBundleBuilder


class SyncService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._config = ConfigBundleBuilder(session)
        self._modules = ModulesBundleBuilder(session)
        self._source_documents = SourceDocumentsBundleBuilder(session)
        self._triggers = TriggersBundleBuilder(session)
        self._gaps = GapsBundleBuilder(session)
        self._chat_faqs = ChatFaqsBundleBuilder(session)
        self._badges = BadgesBundleBuilder(session)
        self._video_progress = VideoProgressBundleBuilder(session)

    async def get_config_bundle(self) -> ConfigSyncBundle:
        return await self._config.build()

    async def get_modules_bundle(
        self,
        *,
        since: datetime,
        tenant_id: int | None = None,
        user_id: int | None = None,
        storage: ObjectStore | None = None,
        settings: Settings | None = None,
    ) -> ModulesSyncBundle:
        return await self._modules.build(
            since=since,
            tenant_id=tenant_id,
            user_id=user_id,
            storage=storage,
            settings=settings,
        )

    async def get_source_documents_bundle(
        self,
        *,
        since: datetime,
        storage: ObjectStore,
        tenant_id: int | None = None,
        user_id: int | None = None,
        settings: Settings | None = None,
    ) -> SourceDocumentsSyncBundle:
        return await self._source_documents.build(
            since=since,
            storage=storage,
            tenant_id=tenant_id,
            user_id=user_id,
            settings=settings,
        )

    async def get_triggers_bundle(
        self,
        *,
        since: datetime,
        tenant_id: int | None = None,
    ) -> TriggersSyncBundle:
        return await self._triggers.build(since=since, tenant_id=tenant_id)

    async def get_gaps_bundle(
        self,
        *,
        since: datetime | None,
        chw_id: int | None,
        tenant_id: int | None = None,
    ) -> GapsSyncBundle:
        return await self._gaps.build(since=since, chw_id=chw_id, tenant_id=tenant_id)

    async def get_chat_faqs_bundle(
        self,
        *,
        since: datetime,
        tenant_id: int | None = None,
    ) -> ChatFaqsSyncBundle:
        return await self._chat_faqs.build(since=since, tenant_id=tenant_id)

    async def get_badges_bundle(
        self,
        *,
        user_id: int,
        tenant_id: int,
        storage: ObjectStore,
        settings: Settings | None = None,
    ) -> BadgesSyncBundle:
        return await self._badges.build(
            user_id=user_id,
            tenant_id=tenant_id,
            storage=storage,
            settings=settings,
        )

    async def get_video_progress_bundle(
        self,
        *,
        since: datetime,
        user_id: int,
        tenant_id: int,
    ) -> VideoProgressSyncBundle:
        return await self._video_progress.build(
            since=since,
            user_id=user_id,
            tenant_id=tenant_id,
        )
