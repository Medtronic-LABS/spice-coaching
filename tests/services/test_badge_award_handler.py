"""BadgeAwardHandler unit/service tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from platform_service.db.models.badge import BADGE_STATUS_DELETED, Badge, BadgeModule
from platform_service.db.models.chw_badge import CHWBadge
from platform_service.db.models.chw_module_quiz_progress import CHWModuleQuizProgress
from platform_service.db.models.module import Module
from platform_service.db.models.module_family import ModuleFamily
from platform_service.db.module_availability import LIFECYCLE_DEACTIVATED
from platform_service.services.module_completion.badge_award_handler import BadgeAwardHandler
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
    status: str = "active",
    name: str | None = None,
) -> Badge:
    badge = Badge(
        name=name or f"badge-{uuid4().hex[:8]}",
        domain="hypertension",
        image_storage_path=f"badges/{uuid4().hex[:8]}.png",
        status=status,
        tenant_id=tenant_id,
    )
    session.add(badge)
    await session.flush()
    for module_id in module_ids:
        session.add(BadgeModule(badge_id=badge.id, module_id=module_id))
    await session.flush()
    return badge


async def _seed_full_coverage(
    session: AsyncSession,
    *,
    chw_id: int,
    module: Module,
    tenant_id: int = 1,
) -> None:
    questions = await _add_quiz_questions(session, module=module, count=1)
    for q in questions:
        session.add(
            CHWModuleQuizProgress(
                chw_id=chw_id,
                module_id=module.id,
                quiz_id=q.id,
                tenant_id=tenant_id,
            )
        )
    await session.flush()


async def test_awards_single_module_badge_when_coverage_complete(
    db_session: AsyncSession,
) -> None:
    module = await _make_module(db_session)
    badge = await _make_badge(db_session, module_ids=[module.id])
    chw = _test_chw_id()
    await _seed_full_coverage(db_session, chw_id=chw, module=module)

    await BadgeAwardHandler(db_session).try_award_for_completed_module(
        chw_id=chw,
        tenant_id=1,
        module_id=module.id,
    )

    row = (
        await db_session.execute(
            select(CHWBadge).where(CHWBadge.chw_id == chw, CHWBadge.badge_id == badge.id)
        )
    ).scalar_one()
    assert row.tenant_id == 1
    assert row.earned_at is not None


async def test_multi_module_badge_requires_all_versions_complete(
    db_session: AsyncSession,
) -> None:
    m1 = await _make_module(db_session)
    m2 = await _make_module(db_session)
    badge = await _make_badge(db_session, module_ids=[m1.id, m2.id])
    chw = _test_chw_id()
    await _seed_full_coverage(db_session, chw_id=chw, module=m1)

    await BadgeAwardHandler(db_session).try_award_for_completed_module(
        chw_id=chw,
        tenant_id=1,
        module_id=m1.id,
    )
    assert (
        await db_session.execute(
            select(func.count())
            .select_from(CHWBadge)
            .where(CHWBadge.chw_id == chw, CHWBadge.badge_id == badge.id)
        )
    ).scalar_one() == 0

    await _seed_full_coverage(db_session, chw_id=chw, module=m2)
    await BadgeAwardHandler(db_session).try_award_for_completed_module(
        chw_id=chw,
        tenant_id=1,
        module_id=m2.id,
    )
    assert (
        await db_session.execute(
            select(func.count())
            .select_from(CHWBadge)
            .where(CHWBadge.chw_id == chw, CHWBadge.badge_id == badge.id)
        )
    ).scalar_one() == 1


async def test_module_linked_to_two_badges_awards_both(
    db_session: AsyncSession,
) -> None:
    module = await _make_module(db_session)
    b1 = await _make_badge(db_session, module_ids=[module.id], name="a")
    b2 = await _make_badge(db_session, module_ids=[module.id], name="b")
    chw = _test_chw_id()
    await _seed_full_coverage(db_session, chw_id=chw, module=module)

    await BadgeAwardHandler(db_session).try_award_for_completed_module(
        chw_id=chw,
        tenant_id=1,
        module_id=module.id,
    )
    awarded = set(
        (await db_session.execute(select(CHWBadge.badge_id).where(CHWBadge.chw_id == chw))).scalars().all()
    )
    assert awarded == {b1.id, b2.id}


async def test_soft_deleted_badge_not_awarded(db_session: AsyncSession) -> None:
    module = await _make_module(db_session)
    badge = await _make_badge(db_session, module_ids=[module.id], status=BADGE_STATUS_DELETED)
    chw = _test_chw_id()
    await _seed_full_coverage(db_session, chw_id=chw, module=module)

    await BadgeAwardHandler(db_session).try_award_for_completed_module(
        chw_id=chw,
        tenant_id=1,
        module_id=module.id,
    )
    assert (
        await db_session.execute(
            select(func.count())
            .select_from(CHWBadge)
            .where(CHWBadge.chw_id == chw, CHWBadge.badge_id == badge.id)
        )
    ).scalar_one() == 0


async def test_empty_badge_never_awarded(db_session: AsyncSession) -> None:
    module = await _make_module(db_session)
    # Empty badge shares no link; create empty badge and ensure completing an
    # unrelated module cannot award it. Also verify explicit empty is skipped
    # if somehow found — empty badges never appear in list_active_badge_ids_for_module.
    empty = await _make_badge(db_session, module_ids=[])
    chw = _test_chw_id()
    await _seed_full_coverage(db_session, chw_id=chw, module=module)

    await BadgeAwardHandler(db_session).try_award_for_completed_module(
        chw_id=chw,
        tenant_id=1,
        module_id=module.id,
    )
    assert (
        await db_session.execute(
            select(func.count())
            .select_from(CHWBadge)
            .where(CHWBadge.chw_id == chw, CHWBadge.badge_id == empty.id)
        )
    ).scalar_one() == 0


async def test_zero_quiz_sibling_blocks_award(db_session: AsyncSession) -> None:
    m_with_quiz = await _make_module(db_session)
    m_no_quiz = await _make_module(db_session)
    badge = await _make_badge(db_session, module_ids=[m_with_quiz.id, m_no_quiz.id])
    chw = _test_chw_id()
    await _seed_full_coverage(db_session, chw_id=chw, module=m_with_quiz)

    await BadgeAwardHandler(db_session).try_award_for_completed_module(
        chw_id=chw,
        tenant_id=1,
        module_id=m_with_quiz.id,
    )
    assert (
        await db_session.execute(
            select(func.count())
            .select_from(CHWBadge)
            .where(CHWBadge.chw_id == chw, CHWBadge.badge_id == badge.id)
        )
    ).scalar_one() == 0


async def test_deactivated_linked_module_is_excluded_from_badge_eligibility(
    db_session: AsyncSession,
) -> None:
    active_module = await _make_module(db_session)
    deactivated_module = await _make_module(db_session)
    deactivated_module.lifecycle_status = LIFECYCLE_DEACTIVATED
    await db_session.flush()

    badge = await _make_badge(
        db_session,
        module_ids=[active_module.id, deactivated_module.id],
    )
    chw = _test_chw_id()
    await _seed_full_coverage(db_session, chw_id=chw, module=active_module)

    await BadgeAwardHandler(db_session).try_award_for_completed_module(
        chw_id=chw,
        tenant_id=1,
        module_id=active_module.id,
    )

    assert (
        await db_session.execute(
            select(func.count())
            .select_from(CHWBadge)
            .where(CHWBadge.chw_id == chw, CHWBadge.badge_id == badge.id)
        )
    ).scalar_one() == 1


async def test_wrong_tenant_badge_not_considered(db_session: AsyncSession) -> None:
    module = await _make_module(db_session)
    badge = await _make_badge(db_session, module_ids=[module.id], tenant_id=99)
    chw = _test_chw_id()
    await _seed_full_coverage(db_session, chw_id=chw, module=module)

    await BadgeAwardHandler(db_session).try_award_for_completed_module(
        chw_id=chw,
        tenant_id=1,
        module_id=module.id,
    )
    assert (
        await db_session.execute(
            select(func.count())
            .select_from(CHWBadge)
            .where(CHWBadge.chw_id == chw, CHWBadge.badge_id == badge.id)
        )
    ).scalar_one() == 0


async def test_already_awarded_is_idempotent(db_session: AsyncSession) -> None:
    module = await _make_module(db_session)
    badge = await _make_badge(db_session, module_ids=[module.id])
    chw = _test_chw_id()
    await _seed_full_coverage(db_session, chw_id=chw, module=module)

    handler = BadgeAwardHandler(db_session)
    await handler.try_award_for_completed_module(chw_id=chw, tenant_id=1, module_id=module.id)
    await handler.try_award_for_completed_module(chw_id=chw, tenant_id=1, module_id=module.id)
    assert (
        await db_session.execute(
            select(func.count())
            .select_from(CHWBadge)
            .where(CHWBadge.chw_id == chw, CHWBadge.badge_id == badge.id)
        )
    ).scalar_one() == 1


async def test_exact_version_required_not_other_family_version(
    db_session: AsyncSession,
) -> None:
    family = ModuleFamily(module_code=f"WRK-{uuid4().hex[:8]}", tenant_id=1)
    db_session.add(family)
    await db_session.flush()

    v1 = Module(
        module_family_id=family.id,
        version=1,
        lifecycle_status="published",
        module_type="refresher",
        title_localized={"bn": "v1"},
        domain="hypertension",
        estimated_minutes=5,
        difficulty_level="basic",
        tenant_id=1,
    )
    v2 = Module(
        module_family_id=family.id,
        version=2,
        lifecycle_status="published",
        module_type="refresher",
        title_localized={"bn": "v2"},
        domain="hypertension",
        estimated_minutes=5,
        difficulty_level="basic",
        tenant_id=1,
    )
    db_session.add_all([v1, v2])
    await db_session.flush()
    family.current_published_module_id = v2.id
    await db_session.flush()

    badge = await _make_badge(db_session, module_ids=[v1.id])
    chw = _test_chw_id()
    await _seed_full_coverage(db_session, chw_id=chw, module=v2)

    await BadgeAwardHandler(db_session).try_award_for_completed_module(
        chw_id=chw,
        tenant_id=1,
        module_id=v2.id,
    )
    assert (
        await db_session.execute(
            select(func.count())
            .select_from(CHWBadge)
            .where(CHWBadge.chw_id == chw, CHWBadge.badge_id == badge.id)
        )
    ).scalar_one() == 0

    await _seed_full_coverage(db_session, chw_id=chw, module=v1)
    await BadgeAwardHandler(db_session).try_award_for_completed_module(
        chw_id=chw,
        tenant_id=1,
        module_id=v1.id,
    )
    assert (
        await db_session.execute(
            select(func.count())
            .select_from(CHWBadge)
            .where(CHWBadge.chw_id == chw, CHWBadge.badge_id == badge.id)
        )
    ).scalar_one() == 1


async def test_missing_tenant_id_skips(db_session: AsyncSession) -> None:
    module = await _make_module(db_session)
    badge = await _make_badge(db_session, module_ids=[module.id])
    chw = _test_chw_id()
    await _seed_full_coverage(db_session, chw_id=chw, module=module)

    await BadgeAwardHandler(db_session).try_award_for_completed_module(
        chw_id=chw,
        tenant_id=None,
        module_id=module.id,
    )
    assert (
        await db_session.execute(
            select(func.count())
            .select_from(CHWBadge)
            .where(CHWBadge.chw_id == chw, CHWBadge.badge_id == badge.id)
        )
    ).scalar_one() == 0
