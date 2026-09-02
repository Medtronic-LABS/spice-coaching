"""Per-question quiz progress and module completion coverage."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.default_tenant import DEFAULT_TENANT_ID
from platform_service.db.models.chw_module_completion import CHWModuleCompletion
from platform_service.db.models.chw_module_quiz_progress import CHWModuleQuizProgress
from platform_service.db.models.module import Module
from platform_service.db.models.module_quiz_question import ModuleQuizQuestion
from platform_service.db.repositories.module_completion_repository import (
    ModuleCompletionRepository,
)
from platform_service.services.module_completion.quiz_coverage import quiz_coverage_count

logger = logging.getLogger(__name__)


class QuizProgressHandler:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_question_attempted_and_maybe_complete(
        self,
        *,
        chw_id: int,
        tenant_id: int | None,
        module: Module,
        quiz_id: UUID,
    ) -> bool:
        """Persist per-question progress; mark completed when coverage hits 100%.

        Returns True only when this attempt newly completes the module version
        (coverage crossed from incomplete to complete).
        """
        if not await self._validate_quiz_belongs_to_module(module=module, quiz_id=quiz_id):
            return False

        effective_tenant = tenant_id if tenant_id is not None else DEFAULT_TENANT_ID

        quiz_ids, covered_before = await quiz_coverage_count(
            self._session, chw_id=chw_id, module_id=module.id
        )

        # Idempotent upsert: (chw_id, module_id, quiz_id) PK.
        stmt = (
            insert(CHWModuleQuizProgress)
            .values(
                chw_id=chw_id,
                module_id=module.id,
                quiz_id=quiz_id,
                tenant_id=effective_tenant,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    CHWModuleQuizProgress.chw_id,
                    CHWModuleQuizProgress.module_id,
                    CHWModuleQuizProgress.quiz_id,
                ]
            )
        )
        await self._session.execute(stmt)

        if not quiz_ids:
            return False

        _, covered_after = await quiz_coverage_count(self._session, chw_id=chw_id, module_id=module.id)
        if covered_after < len(quiz_ids):
            return False

        repo = ModuleCompletionRepository(self._session)
        comp = await repo.get(chw_id=chw_id, module_family_id=module.module_family_id)
        if comp is None:
            self._session.add(
                CHWModuleCompletion(
                    chw_id=chw_id,
                    module_family_id=module.module_family_id,
                    tenant_id=effective_tenant,
                    attempts_since_last_pass=0,
                )
            )
            await self._session.flush()
        await repo.mark_completed(
            chw_id=chw_id,
            module_family_id=module.module_family_id,
            completed_module_id=module.id,
        )
        return covered_before < len(quiz_ids)

    async def _validate_quiz_belongs_to_module(
        self,
        *,
        module: Module,
        quiz_id: UUID,
    ) -> bool:
        quiz_row = await self._session.get(ModuleQuizQuestion, quiz_id)
        if quiz_row is None or quiz_row.module_id != module.id:
            logger.warning(
                "module_completion: quiz_id=%s not found for module_id=%s; skipping progress",
                quiz_id,
                module.id,
            )
            return False
        return True
