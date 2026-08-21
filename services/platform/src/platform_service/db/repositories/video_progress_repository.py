"""Repository for CHWVideoProgress — upsert and bulk-read operations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.default_tenant import DEFAULT_TENANT_ID
from platform_service.db.models.chw_video_progress import CHWVideoProgress
from platform_service.db.models.document_assignment import DocumentAssignment
from platform_service.db.models.source_document import SourceDocument


class VideoProgressRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        chw_id: int,
        source_document_id: UUID,
        last_position_ms: int,
        percent_watched: float,
        completed: bool,
        tenant_id: int = DEFAULT_TENANT_ID,
    ) -> CHWVideoProgress:
        """Insert or monotonically merge progress for a single (chw, video) pair.

        On conflict:
        - ``percent_watched`` = max(existing, incoming)
        - ``completed`` = existing OR incoming
        - ``last_position_ms`` from the side with higher percent (tie → max position)
        """
        now = datetime.now(UTC)
        insert_stmt = insert(CHWVideoProgress).values(
            id=uuid.uuid4(),
            chw_id=chw_id,
            source_document_id=source_document_id,
            last_position_ms=last_position_ms,
            percent_watched=percent_watched,
            completed=completed,
            last_watched_at=now,
            tenant_id=tenant_id,
            created_at=now,
            updated_at=now,
        )
        excluded = insert_stmt.excluded
        stmt = insert_stmt.on_conflict_do_update(
            constraint="uq_video_progress_chw_video",
            set_={
                "percent_watched": func.greatest(
                    CHWVideoProgress.percent_watched,
                    excluded.percent_watched,
                ),
                "completed": or_(CHWVideoProgress.completed, excluded.completed),
                "last_position_ms": case(
                    (
                        excluded.percent_watched > CHWVideoProgress.percent_watched,
                        excluded.last_position_ms,
                    ),
                    (
                        excluded.percent_watched < CHWVideoProgress.percent_watched,
                        CHWVideoProgress.last_position_ms,
                    ),
                    else_=func.greatest(
                        CHWVideoProgress.last_position_ms,
                        excluded.last_position_ms,
                    ),
                ),
                "last_watched_at": now,
                "updated_at": now,
            },
        ).returning(CHWVideoProgress)
        # populate_existing: RETURNING must refresh the identity-map instance when
        # the same (chw, video) row is upserted more than once in one session.
        result = await self._session.execute(
            stmt,
            execution_options={"populate_existing": True},
        )
        await self._session.flush()
        return result.scalar_one()

    async def get_by_chw_and_videos(
        self,
        chw_id: int,
        video_ids: list[UUID],
    ) -> dict[UUID, CHWVideoProgress]:
        """Return a mapping of source_document_id → progress row for the given user."""
        if not video_ids:
            return {}
        stmt = select(CHWVideoProgress).where(
            CHWVideoProgress.chw_id == chw_id,
            CHWVideoProgress.source_document_id.in_(video_ids),
        )
        rows = list((await self._session.execute(stmt)).scalars().all())
        return {row.source_document_id: row for row in rows}

    async def list_assigned_videos_updated_since(
        self,
        *,
        chw_id: int,
        tenant_id: int,
        since: datetime,
    ) -> list[CHWVideoProgress]:
        """Progress rows for still-assigned video documents with ``updated_at > since``.

        Intersection of ``chw_video_progress``, current ``document_assignment``, and
        ``source_document.source_type == 'video'``, scoped to CHW + tenant.
        """
        stmt = (
            select(CHWVideoProgress)
            .join(
                DocumentAssignment,
                (DocumentAssignment.source_document_id == CHWVideoProgress.source_document_id)
                & (DocumentAssignment.user_id == CHWVideoProgress.chw_id),
            )
            .join(
                SourceDocument,
                SourceDocument.id == CHWVideoProgress.source_document_id,
            )
            .where(
                CHWVideoProgress.chw_id == chw_id,
                CHWVideoProgress.tenant_id == tenant_id,
                CHWVideoProgress.updated_at > since,
                SourceDocument.source_type == "video",
            )
            .order_by(CHWVideoProgress.updated_at.asc())
        )
        return list((await self._session.execute(stmt)).scalars().all())
