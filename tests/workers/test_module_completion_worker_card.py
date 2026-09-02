"""module_completion_worker — module_card_viewed progress and card-only completion."""

from __future__ import annotations

from uuid import uuid4

import pytest
from platform_service.db.models.chw_module_card_progress import CHWModuleCardProgress
from platform_service.db.models.chw_module_completion import CHWModuleCompletion
from platform_service.workers import module_completion_worker
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db
from tests.workers.conftest import (
    _add_module_cards,
    _add_quiz_questions,
    _make_module,
    _test_chw_id,
)

pytestmark = [pytest.mark.asyncio, requires_db]


@pytest.mark.asyncio
@requires_db
async def test_card_view_records_progress_by_card_id(patch_session_local, db_session: AsyncSession) -> None:
    module = await _make_module(db_session)
    cards = await _add_module_cards(db_session, module=module, count=2)
    chw = _test_chw_id()

    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_card_viewed",
            "event_id": str(uuid4()),
            "chw_id": str(chw),
            "module_id": str(module.id),
            "card_id": str(cards[0].id),
        }
    )

    r = await db_session.execute(
        select(func.count())
        .select_from(CHWModuleCardProgress)
        .where(
            CHWModuleCardProgress.chw_id == chw,
            CHWModuleCardProgress.module_id == module.id,
            CHWModuleCardProgress.card_id == cards[0].id,
        )
    )
    assert int(r.scalar_one()) == 1

    # Only 1 of 2 cards viewed -> module not yet complete
    r = await db_session.execute(select(CHWModuleCompletion).where(CHWModuleCompletion.chw_id == chw))
    assert r.scalar_one_or_none() is None


@pytest.mark.asyncio
@requires_db
async def test_card_view_records_progress_by_card_family_id(
    patch_session_local, db_session: AsyncSession
) -> None:
    module = await _make_module(db_session)
    cards = await _add_module_cards(db_session, module=module, count=2)
    chw = _test_chw_id()

    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_card_viewed",
            "event_id": str(uuid4()),
            "chw_id": str(chw),
            "module_id": str(module.id),
            "card_family_id": str(cards[0].card_family_id),
        }
    )

    r = await db_session.execute(
        select(func.count())
        .select_from(CHWModuleCardProgress)
        .where(
            CHWModuleCardProgress.chw_id == chw,
            CHWModuleCardProgress.module_id == module.id,
            CHWModuleCardProgress.card_id == cards[0].id,
        )
    )
    assert int(r.scalar_one()) == 1


@pytest.mark.asyncio
@requires_db
async def test_card_only_module_completes_when_all_cards_viewed(
    patch_session_local, db_session: AsyncSession
) -> None:
    module = await _make_module(db_session)
    cards = await _add_module_cards(db_session, module=module, count=2)
    chw = _test_chw_id()

    # View card 1
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_card_viewed",
            "event_id": str(uuid4()),
            "chw_id": str(chw),
            "module_id": str(module.id),
            "card_id": str(cards[0].id),
        }
    )
    r = await db_session.execute(select(CHWModuleCompletion).where(CHWModuleCompletion.chw_id == chw))
    assert r.scalar_one_or_none() is None

    # View card 2 (100% coverage on 0-quiz module)
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_card_viewed",
            "event_id": str(uuid4()),
            "chw_id": str(chw),
            "module_id": str(module.id),
            "card_id": str(cards[1].id),
        }
    )

    r = await db_session.execute(select(CHWModuleCompletion).where(CHWModuleCompletion.chw_id == chw))
    comp = r.scalar_one()
    assert comp.completed_at is not None
    assert comp.latest_completed_module_id == module.id
    assert comp.latest_attempt_passed is True
    assert comp.latest_quiz_score is None
    assert comp.reinforcement_due_at is not None


@pytest.mark.asyncio
@requires_db
async def test_quiz_enabled_module_does_not_complete_from_cards_alone(
    patch_session_local, db_session: AsyncSession
) -> None:
    module = await _make_module(db_session)
    cards = await _add_module_cards(db_session, module=module, count=2)
    quizzes = await _add_quiz_questions(db_session, module=module, count=1)
    chw = _test_chw_id()

    for card in cards:
        await module_completion_worker.process_module_event_job(
            {
                "event_type": "module_card_viewed",
                "event_id": str(uuid4()),
                "chw_id": str(chw),
                "module_id": str(module.id),
                "card_id": str(card.id),
            }
        )

    # Both cards viewed, but module has 1 quiz question -> NOT completed
    r = await db_session.execute(select(CHWModuleCompletion).where(CHWModuleCompletion.chw_id == chw))
    assert r.scalar_one_or_none() is None

    # Now attempt the quiz question -> module should complete
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_quiz_attempted",
            "event_id": str(uuid4()),
            "chw_id": str(chw),
            "module_id": str(module.id),
            "quiz_id": str(quizzes[0].id),
            "quiz_score_pct": 0.90,
            "outcome": "correct",
        }
    )

    r = await db_session.execute(select(CHWModuleCompletion).where(CHWModuleCompletion.chw_id == chw))
    comp = r.scalar_one()
    assert comp.completed_at is not None
    assert comp.latest_completed_module_id == module.id


@pytest.mark.asyncio
@requires_db
async def test_card_view_duplicate_is_idempotent(patch_session_local, db_session: AsyncSession) -> None:
    module = await _make_module(db_session)
    cards = await _add_module_cards(db_session, module=module, count=1)
    chw = _test_chw_id()

    payload = {
        "event_type": "module_card_viewed",
        "event_id": str(uuid4()),
        "chw_id": str(chw),
        "module_id": str(module.id),
        "card_id": str(cards[0].id),
    }
    await module_completion_worker.process_module_event_job(payload)
    await module_completion_worker.process_module_event_job({**payload, "event_id": str(uuid4())})

    r = await db_session.execute(
        select(func.count())
        .select_from(CHWModuleCardProgress)
        .where(CHWModuleCardProgress.chw_id == chw, CHWModuleCardProgress.module_id == module.id)
    )
    assert int(r.scalar_one()) == 1
