"""module_completion_worker — badge award on module version completion."""

from __future__ import annotations

from uuid import uuid4

import pytest
from platform_service.db.models.badge import Badge, BadgeModule
from platform_service.db.models.chw_badge import CHWBadge
from platform_service.db.models.module import Module
from platform_service.workers import module_completion_worker
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db
from tests.workers.conftest import _add_quiz_questions, _make_module, _test_chw_id

pytestmark = [pytest.mark.asyncio, requires_db]


async def _make_badge(
    session: AsyncSession,
    *,
    module_ids: list,
    tenant_id: int = 1,
    name: str | None = None,
) -> Badge:
    badge = Badge(
        name=name or f"badge-{uuid4().hex[:8]}",
        domain="hypertension",
        image_storage_path=f"badges/{uuid4().hex[:8]}.png",
        status="active",
        tenant_id=tenant_id,
    )
    session.add(badge)
    await session.flush()
    for module_id in module_ids:
        session.add(BadgeModule(badge_id=badge.id, module_id=module_id))
    await session.flush()
    return badge


async def _attempt(
    *,
    chw: int,
    module: Module,
    quiz_id,
    tenant_id: int = 1,
) -> None:
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_quiz_attempted",
            "event_id": str(uuid4()),
            "chw_id": str(chw),
            "tenant_id": tenant_id,
            "module_id": str(module.id),
            "quiz_id": str(quiz_id),
            "quiz_score_pct": 0.10,
            "outcome": "correct",
        }
    )


@pytest.mark.asyncio
@requires_db
async def test_worker_awards_badge_when_last_question_completes_module(
    patch_session_local, db_session: AsyncSession
) -> None:
    module = await _make_module(db_session, primary_gap_id=None)
    q1, q2 = await _add_quiz_questions(db_session, module=module, count=2)
    badge = await _make_badge(db_session, module_ids=[module.id])
    chw = _test_chw_id()

    await _attempt(chw=chw, module=module, quiz_id=q1.id)
    assert (
        await db_session.execute(
            select(func.count())
            .select_from(CHWBadge)
            .where(CHWBadge.chw_id == chw, CHWBadge.badge_id == badge.id)
        )
    ).scalar_one() == 0

    await _attempt(chw=chw, module=module, quiz_id=q2.id)
    assert (
        await db_session.execute(
            select(func.count())
            .select_from(CHWBadge)
            .where(CHWBadge.chw_id == chw, CHWBadge.badge_id == badge.id)
        )
    ).scalar_one() == 1


@pytest.mark.asyncio
@requires_db
async def test_worker_multi_module_badge_awards_on_final_module(
    patch_session_local, db_session: AsyncSession
) -> None:
    m1 = await _make_module(db_session, primary_gap_id=None)
    m2 = await _make_module(db_session, primary_gap_id=None)
    q1 = (await _add_quiz_questions(db_session, module=m1, count=1))[0]
    q2 = (await _add_quiz_questions(db_session, module=m2, count=1))[0]
    badge = await _make_badge(db_session, module_ids=[m1.id, m2.id])
    chw = _test_chw_id()

    await _attempt(chw=chw, module=m1, quiz_id=q1.id)
    assert (
        await db_session.execute(
            select(func.count())
            .select_from(CHWBadge)
            .where(CHWBadge.chw_id == chw, CHWBadge.badge_id == badge.id)
        )
    ).scalar_one() == 0

    await _attempt(chw=chw, module=m2, quiz_id=q2.id)
    assert (
        await db_session.execute(
            select(func.count())
            .select_from(CHWBadge)
            .where(CHWBadge.chw_id == chw, CHWBadge.badge_id == badge.id)
        )
    ).scalar_one() == 1


@pytest.mark.asyncio
@requires_db
async def test_worker_awards_multiple_badges_for_same_module(
    patch_session_local, db_session: AsyncSession
) -> None:
    module = await _make_module(db_session, primary_gap_id=None)
    q1 = (await _add_quiz_questions(db_session, module=module, count=1))[0]
    b1 = await _make_badge(db_session, module_ids=[module.id], name="one")
    b2 = await _make_badge(db_session, module_ids=[module.id], name="two")
    chw = _test_chw_id()

    await _attempt(chw=chw, module=module, quiz_id=q1.id)
    awarded = set(
        (await db_session.execute(select(CHWBadge.badge_id).where(CHWBadge.chw_id == chw))).scalars().all()
    )
    assert awarded == {b1.id, b2.id}


@pytest.mark.asyncio
@requires_db
async def test_worker_duplicate_event_claim_does_not_double_award(
    patch_session_local, db_session: AsyncSession
) -> None:
    module = await _make_module(db_session, primary_gap_id=None)
    q1 = (await _add_quiz_questions(db_session, module=module, count=1))[0]
    badge = await _make_badge(db_session, module_ids=[module.id])
    chw = _test_chw_id()
    event_id = str(uuid4())
    payload = {
        "event_type": "module_quiz_attempted",
        "event_id": event_id,
        "chw_id": str(chw),
        "tenant_id": 1,
        "module_id": str(module.id),
        "quiz_id": str(q1.id),
        "quiz_score_pct": 0.10,
        "outcome": "correct",
    }
    await module_completion_worker.process_module_event_job(payload)
    await module_completion_worker.process_module_event_job(payload)
    assert (
        await db_session.execute(
            select(func.count())
            .select_from(CHWBadge)
            .where(CHWBadge.chw_id == chw, CHWBadge.badge_id == badge.id)
        )
    ).scalar_one() == 1
