"""Build card embedding sync bundles for device sync."""

from __future__ import annotations

from datetime import UTC, datetime

from mc_contracts.sync import CardEmbeddingsSyncBundle, CardEmbeddingSyncPayload
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.config import Settings, get_settings
from platform_service.db.repositories.module_repository import ModuleRepository


class CardEmbeddingsBundleBuilder:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def build(
        self,
        *,
        since: datetime,
        tenant_id: int | None = None,
        settings: Settings | None = None,
    ) -> CardEmbeddingsSyncBundle:
        settings = settings or get_settings()
        rows = await ModuleRepository(self._session).list_card_embeddings_for_sync(
            since,
            tenant_id=tenant_id,
        )
        return CardEmbeddingsSyncBundle(
            cards=[
                CardEmbeddingSyncPayload(
                    card_id=row.id,
                    module_id=row.module_id,
                    card_family_id=row.card_family_id,
                    embedding=list(row.local_embedding),
                )
                for row in rows
            ],
            embedding_dimension=settings.embedding_dimension,
            server_time_utc=datetime.now(UTC).isoformat(),
        )
