"""Retire-heuristic policy for cross-source fusion constituents."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.config import get_settings
from platform_service.db.repositories.module_repository import ModuleRepository
from platform_service.localized import deployment_locales

logger = logging.getLogger(__name__)


class FusionRetirePolicy:
    """Find published modules whose source candidate was a constituent
    of a fusion group; mark them retired.

    Heuristic match: primary-locale title == candidate.proposed_title AND
    candidate's source_document_id is in module.source_document_ids
    AND lifecycle_status = 'published'. No candidate→module FK exists
    in the schema today (modules know their source DOCS, not their
    source CANDIDATE); the heuristic is precise enough because every
    per-source candidate produces exactly one module whose primary title
    matches proposed_title.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._modules = ModuleRepository(session)

    async def retire_constituent_modules(
        self,
        constituent_ids: list[UUID],
        candidates_by_id: dict[str, dict[str, Any]],
    ) -> int:
        if not constituent_ids:
            return 0
        retired = 0
        for cid in constituent_ids:
            c = candidates_by_id.get(str(cid))
            if c is None:
                continue
            title = c.get("proposed_title", "")
            sd_id = c.get("source_document_id")
            if not title or not sd_id:
                continue
            title_locale = deployment_locales(get_settings())
            title_filter = json.dumps({title_locale: title})
            result = await self._session.execute(
                text("""
                    SELECT id
                    FROM module
                    WHERE lifecycle_status = 'published'
                      AND title_localized @> CAST(:title_filter AS jsonb)
                      AND :sd_id = ANY(source_document_ids)
                """),
                {"title_filter": title_filter, "sd_id": str(sd_id)},
            )
            module_ids = list(result.scalars().all())
            for module_id in module_ids:
                await self._modules.retire_module(module_id)
            n = len(module_ids)
            if n:
                logger.info(
                    "Stage 2b runner: retired %d constituent module(s) titled %r (source %s)",
                    n,
                    title,
                    sd_id[:8] if sd_id else "?",
                )
            retired += n
        return retired
