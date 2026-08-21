"""Build video progress sync bundles for device sync."""

from __future__ import annotations

from datetime import UTC, datetime

from mc_contracts.sync import VideoProgressPayload, VideoProgressSyncBundle
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.repositories.video_progress_repository import VideoProgressRepository


class VideoProgressBundleBuilder:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def build(
        self,
        *,
        since: datetime,
        user_id: int,
        tenant_id: int,
    ) -> VideoProgressSyncBundle:
        rows = await VideoProgressRepository(self._session).list_assigned_videos_updated_since(
            chw_id=user_id,
            tenant_id=tenant_id,
            since=since,
        )
        return VideoProgressSyncBundle(
            videos=[
                VideoProgressPayload(
                    source_document_id=row.source_document_id,
                    last_position_ms=row.last_position_ms,
                    percent_watched=row.percent_watched,
                    completed=row.completed,
                    last_watched_at=row.last_watched_at,
                )
                for row in rows
            ],
            server_time_utc=datetime.now(UTC).isoformat(),
        )
