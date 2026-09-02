"""CHW-scoped read queries for device sync bundles."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.chw_behavioural_gap_state import CHWBehaviouralGapState
from platform_service.db.models.chw_module_card_progress import CHWModuleCardProgress
from platform_service.db.models.chw_module_quiz_progress import CHWModuleQuizProgress
from platform_service.db.models.chw_quiz_question_state import CHWQuizQuestionState
from platform_service.db.models.module import Module
from platform_service.db.models.module_card import ModuleCard
from platform_service.db.models.module_quiz_question import ModuleQuizQuestion


class CHWSyncRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_gap_states_for_chw(
        self,
        *,
        chw_id: int,
        since: datetime | None,
    ) -> list[CHWBehaviouralGapState]:
        stmt = select(CHWBehaviouralGapState).where(CHWBehaviouralGapState.chw_id == chw_id)
        if since is not None:
            stmt = stmt.where(
                CHWBehaviouralGapState.updated_at.is_not(None),
                CHWBehaviouralGapState.updated_at > since,
            )
        stmt = stmt.order_by(
            CHWBehaviouralGapState.updated_at.asc().nullslast(),
            CHWBehaviouralGapState.behavioural_gap_id.asc(),
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_quiz_question_states_for_chw(
        self,
        *,
        chw_id: int,
        since: datetime | None,
    ) -> list[CHWQuizQuestionState]:
        stmt = select(CHWQuizQuestionState).where(CHWQuizQuestionState.chw_id == chw_id)
        if since is not None:
            stmt = stmt.where(
                CHWQuizQuestionState.updated_at.is_not(None),
                CHWQuizQuestionState.updated_at > since,
            )
        stmt = stmt.order_by(
            CHWQuizQuestionState.updated_at.asc().nullslast(),
            CHWQuizQuestionState.quiz_id.asc(),
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_module_ids_with_quiz_progress(
        self,
        *,
        chw_id: int,
        since: datetime | None,
    ) -> list[UUID]:
        stmt = (
            select(CHWModuleQuizProgress.module_id).where(CHWModuleQuizProgress.chw_id == chw_id).distinct()
        )
        if since is not None:
            stmt = stmt.where(CHWModuleQuizProgress.first_correct_at > since)
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_module_ids_with_card_progress(
        self,
        *,
        chw_id: int,
        since: datetime | None,
    ) -> list[UUID]:
        stmt = (
            select(CHWModuleCardProgress.module_id).where(CHWModuleCardProgress.chw_id == chw_id).distinct()
        )
        if since is not None:
            stmt = stmt.where(CHWModuleCardProgress.first_viewed_at > since)
        return list((await self._session.execute(stmt)).scalars().all())

    async def tenant_id_by_module_for_chw(
        self,
        *,
        chw_id: int,
        module_ids: list[UUID],
    ) -> dict[UUID, int]:
        if not module_ids:
            return {}
        tenant_rows = (
            await self._session.execute(
                select(Module.id, Module.tenant_id).where(
                    Module.id.in_(module_ids),
                )
            )
        ).all()
        tenant_by_module: dict[UUID, int] = {}
        for module_id, tenant_id in tenant_rows:
            if tenant_id is not None and module_id not in tenant_by_module:
                tenant_by_module[module_id] = tenant_id
        return tenant_by_module

    async def list_incomplete_quiz_rows(
        self,
        *,
        chw_id: int,
        module_ids: list[UUID],
    ) -> list[tuple[UUID, UUID, UUID]]:
        """Return (module_id, quiz_id, module_family_id) for unanswered questions."""
        if not module_ids:
            return []
        progress_exists = exists().where(
            CHWModuleQuizProgress.chw_id == chw_id,
            CHWModuleQuizProgress.module_id == ModuleQuizQuestion.module_id,
            CHWModuleQuizProgress.quiz_id == ModuleQuizQuestion.id,
        )
        rows = (
            await self._session.execute(
                select(
                    ModuleQuizQuestion.module_id,
                    ModuleQuizQuestion.id,
                    Module.module_family_id,
                )
                .join(Module, Module.id == ModuleQuizQuestion.module_id)
                .where(
                    ModuleQuizQuestion.module_id.in_(module_ids),
                    ~progress_exists,
                )
                .order_by(
                    ModuleQuizQuestion.module_id.asc(),
                    ModuleQuizQuestion.question_order.asc().nullslast(),
                    ModuleQuizQuestion.id.asc(),
                )
            )
        ).all()
        return [(module_id, quiz_id, module_family_id) for module_id, quiz_id, module_family_id in rows]

    async def list_incomplete_card_rows(
        self,
        *,
        chw_id: int,
        module_ids: list[UUID],
    ) -> list[tuple[UUID, UUID, UUID]]:
        """Return (module_id, card_id, module_family_id) for unviewed cards."""
        if not module_ids:
            return []
        progress_exists = exists().where(
            CHWModuleCardProgress.chw_id == chw_id,
            CHWModuleCardProgress.module_id == ModuleCard.module_id,
            CHWModuleCardProgress.card_id == ModuleCard.id,
        )
        rows = (
            await self._session.execute(
                select(
                    ModuleCard.module_id,
                    ModuleCard.id,
                    Module.module_family_id,
                )
                .join(Module, Module.id == ModuleCard.module_id)
                .where(
                    ModuleCard.module_id.in_(module_ids),
                    ~progress_exists,
                )
                .order_by(
                    ModuleCard.module_id.asc(),
                    ModuleCard.card_order.asc(),
                    ModuleCard.id.asc(),
                )
            )
        ).all()
        return [(module_id, card_id, module_family_id) for module_id, card_id, module_family_id in rows]
