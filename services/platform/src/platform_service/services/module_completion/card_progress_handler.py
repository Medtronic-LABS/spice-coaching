"""Per-card view progress and module completion coverage for card-only modules."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.default_tenant import DEFAULT_TENANT_ID
from platform_service.db.models.chw_module_card_progress import CHWModuleCardProgress
from platform_service.db.models.module import Module
from platform_service.db.models.module_card import ModuleCard
from platform_service.db.repositories.module_completion_repository import (
    ModuleCompletionRepository,
)
from platform_service.services.module_completion.card_coverage import card_coverage_count
from platform_service.services.module_completion.quiz_coverage import quiz_coverage_count

logger = logging.getLogger(__name__)


class CardProgressHandler:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_card_viewed_and_maybe_complete(
        self,
        *,
        chw_id: int,
        tenant_id: int | None,
        module: Module,
        card_id: UUID | None = None,
        card_family_id: UUID | None = None,
    ) -> bool:
        """Persist per-card progress; mark completed when card-only module coverage hits 100%.

        Returns True only when this card view newly completes the module version
        (coverage crossed from incomplete to complete on a module with 0 quizzes).
        """
        resolved_card_id = await self._resolve_card_id(
            module=module,
            card_id=card_id,
            card_family_id=card_family_id,
        )
        if resolved_card_id is None:
            return False

        effective_tenant = tenant_id if tenant_id is not None else DEFAULT_TENANT_ID

        card_ids, covered_before = await card_coverage_count(
            self._session, chw_id=chw_id, module_id=module.id
        )

        # Idempotent upsert: (chw_id, module_id, card_id) PK.
        stmt = (
            insert(CHWModuleCardProgress)
            .values(
                chw_id=chw_id,
                module_id=module.id,
                card_id=resolved_card_id,
                tenant_id=effective_tenant,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    CHWModuleCardProgress.chw_id,
                    CHWModuleCardProgress.module_id,
                    CHWModuleCardProgress.card_id,
                ]
            )
        )
        await self._session.execute(stmt)

        if not card_ids:
            return False

        # Only auto-complete modules that have NO quiz questions.
        quiz_ids, _ = await quiz_coverage_count(self._session, chw_id=chw_id, module_id=module.id)
        if quiz_ids:
            # Module has quizzes; completion is driven by quiz attempts instead.
            return False

        _, covered_after = await card_coverage_count(self._session, chw_id=chw_id, module_id=module.id)
        if covered_after < len(card_ids):
            return False

        repo = ModuleCompletionRepository(self._session)
        await repo.record_card_only_completion(
            chw_id=chw_id,
            module_family_id=module.module_family_id,
            completed_module_id=module.id,
            tenant_id=effective_tenant,
        )
        return covered_before < len(card_ids)

    async def _resolve_card_id(
        self,
        *,
        module: Module,
        card_id: UUID | None,
        card_family_id: UUID | None,
    ) -> UUID | None:
        if card_id is not None:
            card_row = await self._session.get(ModuleCard, card_id)
            if card_row is not None and card_row.module_id == module.id:
                return card_row.id
            logger.warning(
                "card_progress: card_id=%s not found for module_id=%s",
                card_id,
                module.id,
            )
            return None

        if card_family_id is not None:
            result = await self._session.execute(
                select(ModuleCard.id).where(
                    ModuleCard.module_id == module.id,
                    ModuleCard.card_family_id == card_family_id,
                )
            )
            found = result.scalar_one_or_none()
            if found is not None:
                return found
            logger.warning(
                "card_progress: card_family_id=%s not found for module_id=%s",
                card_family_id,
                module.id,
            )
            return None

        logger.warning(
            "card_progress: neither card_id nor card_family_id provided for module_id=%s",
            module.id,
        )
        return None
