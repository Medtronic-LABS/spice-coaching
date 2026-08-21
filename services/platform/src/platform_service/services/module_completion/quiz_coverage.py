"""Shared quiz-question coverage checks for a CHW × module version."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.chw_module_quiz_progress import CHWModuleQuizProgress
from platform_service.db.models.module_quiz_question import ModuleQuizQuestion


async def quiz_coverage_count(
    session: AsyncSession,
    *,
    chw_id: int,
    module_id: UUID,
) -> tuple[list[UUID], int]:
    """Return (quiz_ids for module version, distinct progress rows covering them)."""
    quiz_ids = list(
        (
            await session.execute(
                select(ModuleQuizQuestion.id).where(ModuleQuizQuestion.module_id == module_id)
            )
        )
        .scalars()
        .all()
    )
    if not quiz_ids:
        return quiz_ids, 0

    covered_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(CHWModuleQuizProgress)
                .where(
                    CHWModuleQuizProgress.chw_id == chw_id,
                    CHWModuleQuizProgress.module_id == module_id,
                    CHWModuleQuizProgress.quiz_id.in_(quiz_ids),
                )
            )
        ).scalar_one()
    )
    return quiz_ids, covered_count


async def is_module_quiz_coverage_complete(
    session: AsyncSession,
    *,
    chw_id: int,
    module_id: UUID,
) -> bool:
    """True when the module has ≥1 quiz question and the CHW has attempted all of them.

    Modules with zero quiz questions never count as complete.
    """
    quiz_ids, covered_count = await quiz_coverage_count(session, chw_id=chw_id, module_id=module_id)
    return bool(quiz_ids) and covered_count >= len(quiz_ids)
