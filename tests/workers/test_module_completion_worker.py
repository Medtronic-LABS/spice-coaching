"""W-10 — module_completion_worker integration tests.

These tests bypass the Celery shim and call the async job function
directly so we can test the DB side-effects without standing up a broker.
We also patch SessionLocal so the worker uses the same db_session as the
test fixture (it normally creates its own session).
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from platform_service.db.models.behavioural_gap import BehaviouralGap
from platform_service.db.models.chw_behavioural_gap_state import CHWBehaviouralGapState
from platform_service.db.models.chw_learning_point_event import CHWLearningPointEvent
from platform_service.db.models.chw_module_completion import CHWModuleCompletion
from platform_service.db.models.module import Module
from platform_service.db.models.module_family import ModuleFamily
from platform_service.services.learning_points_thresholds import (
    LEARNING_POINTS_THRESHOLD_DEFAULTS,
    learning_points_delta_for_event,
)
from platform_service.workers import module_completion_worker
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db


def _test_chw_id() -> int:
    return uuid4().int % (10**15) + 1


@pytest.fixture
def patch_session_local(db_session: AsyncSession):
    """Make module_completion_worker.SessionLocal yield our test session."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _factory():
        # Disable internal commit so the test's rollback fixture cleans up.
        original_commit = db_session.commit

        async def _commit_as_flush() -> None:
            await db_session.flush()

        db_session.commit = _commit_as_flush  # type: ignore[method-assign]
        try:
            yield db_session
        finally:
            db_session.commit = original_commit  # type: ignore[method-assign]

    with patch.object(module_completion_worker, "SessionLocal", _factory):
        yield


async def _make_module(
    session: AsyncSession,
    *,
    primary_gap_id=None,
    version: int = 1,
) -> Module:
    family = ModuleFamily(module_code=f"WRK-{uuid4().hex[:8]}")
    session.add(family)
    await session.flush()
    module = Module(
        module_family_id=family.id,
        version=version,
        lifecycle_status="published",
        module_type="refresher",
        title_bn="মডিউল",
        domain="hypertension",
        estimated_minutes=5,
        difficulty_level="basic",
        primary_gap_id=primary_gap_id,
    )
    session.add(module)
    await session.flush()
    family.current_published_module_id = module.id
    await session.flush()
    return module


async def _make_gap(session: AsyncSession) -> BehaviouralGap:
    gap = BehaviouralGap(
        gap_code=f"wrk_gap_{uuid4().hex[:8]}",
        description="x",
        domain="hypertension",
        detection_rule_jsonb={},
    )
    session.add(gap)
    await session.flush()
    return gap


# ── unhandled / partial events ──────────────────────────────────────────


@pytest.mark.asyncio
@requires_db
async def test_unhandled_event_type_no_op(patch_session_local, db_session: AsyncSession) -> None:
    await module_completion_worker.process_module_event_job(
        {"event_type": "card_shown", "chw_id": _test_chw_id(), "module_id": str(uuid4())}
    )
    # No state change to assert; just ensure it doesn't raise.


@pytest.mark.asyncio
@requires_db
async def test_module_delivered_awards_learning_points_no_completion_row(
    patch_session_local, db_session: AsyncSession
) -> None:
    chw = _test_chw_id()
    ev = str(uuid4())
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_delivered",
            "event_id": ev,
            "chw_id": chw,
            "module_id": str(uuid4()),
        }
    )
    r = await db_session.execute(select(CHWModuleCompletion))
    assert r.first() is None
    total = (
        await db_session.execute(
            select(func.coalesce(func.sum(CHWLearningPointEvent.points), 0)).where(
                CHWLearningPointEvent.chw_id == chw
            )
        )
    ).scalar_one()
    assert int(total) >= 1


@pytest.mark.asyncio
@requires_db
async def test_quiz_passing_score_without_outcome_does_not_award_learning_points(
    patch_session_local, db_session: AsyncSession
) -> None:
    gap = await _make_gap(db_session)
    module = await _make_module(db_session, primary_gap_id=gap.id)
    chw = _test_chw_id()
    ev = uuid4()
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_quiz_attempted",
            "event_id": str(ev),
            "chw_id": chw,
            "module_id": str(module.id),
            "quiz_score_pct": 0.95,
        }
    )
    r = await db_session.execute(select(CHWLearningPointEvent).where(CHWLearningPointEvent.event_id == ev))
    assert r.scalar_one_or_none() is None


@pytest.mark.asyncio
@requires_db
async def test_quiz_outcome_correct_awards_learning_points_with_score_bonus(
    patch_session_local, db_session: AsyncSession
) -> None:
    gap = await _make_gap(db_session)
    module = await _make_module(db_session, primary_gap_id=gap.id)
    chw = _test_chw_id()
    ev = uuid4()
    score = 0.2
    expected = learning_points_delta_for_event(
        "module_quiz_attempted",
        quiz_score_pct=score,
        thresholds=LEARNING_POINTS_THRESHOLD_DEFAULTS,
    )
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_quiz_attempted",
            "event_id": str(ev),
            "chw_id": chw,
            "module_id": str(module.id),
            "quiz_score_pct": score,
            "outcome": "correct",
        }
    )
    row = (
        await db_session.execute(select(CHWLearningPointEvent).where(CHWLearningPointEvent.event_id == ev))
    ).scalar_one()
    assert row.points == expected
    assert row.chw_id == chw


@pytest.mark.asyncio
@requires_db
async def test_quiz_outcome_incorrect_high_score_does_not_award_learning_points(
    patch_session_local, db_session: AsyncSession
) -> None:
    gap = await _make_gap(db_session)
    module = await _make_module(db_session, primary_gap_id=gap.id)
    chw = _test_chw_id()
    ev = uuid4()
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_quiz_attempted",
            "event_id": str(ev),
            "chw_id": chw,
            "module_id": str(module.id),
            "quiz_score_pct": 0.99,
            "outcome": "incorrect",
        }
    )
    r = await db_session.execute(select(CHWLearningPointEvent).where(CHWLearningPointEvent.event_id == ev))
    assert r.scalar_one_or_none() is None


@pytest.mark.asyncio
@requires_db
async def test_invalid_chw_id_drops_event(patch_session_local, db_session: AsyncSession) -> None:
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_quiz_attempted",
            "chw_id": "not-an-int",
            "module_id": str(uuid4()),
            "quiz_score_pct": 0.8,
        }
    )
    r = await db_session.execute(select(CHWModuleCompletion))
    assert r.first() is None


@pytest.mark.asyncio
@requires_db
async def test_unknown_module_id_drops_event(patch_session_local, db_session: AsyncSession) -> None:
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_quiz_attempted",
            "chw_id": _test_chw_id(),
            "module_id": str(uuid4()),  # not in DB
            "quiz_score_pct": 0.9,
        }
    )
    r = await db_session.execute(select(CHWModuleCompletion))
    assert r.first() is None


# ── spice_action_observed (gap observation) ─────────────────────────────


@pytest.mark.asyncio
@requires_db
async def test_spice_action_observed_records_gap_observation(
    patch_session_local, db_session: AsyncSession
) -> None:
    gap = await _make_gap(db_session)
    chw = _test_chw_id()
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "spice_action_observed",
            "event_id": "evt-spice-1",
            "chw_id": str(chw),
            "payload_json": {
                "kind": "assessment_submitted",
                "behavioural_gap_id": str(gap.id),
            },
        }
    )
    r = await db_session.execute(
        select(CHWBehaviouralGapState).where(
            CHWBehaviouralGapState.chw_id == chw,
            CHWBehaviouralGapState.behavioural_gap_id == gap.id,
        )
    )
    state = r.scalar_one()
    assert state.occurrence_count == 1
    assert state.last_observed_at is not None
    assert state.failed_attempts_count == 0


@pytest.mark.asyncio
@requires_db
async def test_spice_action_observed_incorrect_outcome_increments_failed_attempts(
    patch_session_local, db_session: AsyncSession
) -> None:
    gap = await _make_gap(db_session)
    chw = _test_chw_id()
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "spice_action_observed",
            "event_id": "evt-spice-incorrect",
            "chw_id": str(chw),
            "outcome": "incorrect",
            "payload_json": {
                "kind": "assessment_submitted",
                "behavioural_gap_id": str(gap.id),
            },
        }
    )
    r = await db_session.execute(
        select(CHWBehaviouralGapState).where(
            CHWBehaviouralGapState.chw_id == chw,
            CHWBehaviouralGapState.behavioural_gap_id == gap.id,
        )
    )
    state = r.scalar_one()
    assert state.occurrence_count == 1
    assert state.failed_attempts_count == 1


@pytest.mark.asyncio
@requires_db
async def test_spice_action_observed_wrong_outcome_nested_in_payload_json(
    patch_session_local, db_session: AsyncSession
) -> None:
    gap = await _make_gap(db_session)
    chw = _test_chw_id()
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "spice_action_observed",
            "event_id": "evt-spice-wrong",
            "chw_id": str(chw),
            "payload_json": {
                "kind": "assessment_submitted",
                "behavioural_gap_id": str(gap.id),
                "outcome": "wrong",
            },
        }
    )
    r = await db_session.execute(
        select(CHWBehaviouralGapState).where(
            CHWBehaviouralGapState.chw_id == chw,
            CHWBehaviouralGapState.behavioural_gap_id == gap.id,
        )
    )
    state = r.scalar_one()
    assert state.failed_attempts_count == 1


@pytest.mark.asyncio
@requires_db
async def test_spice_action_observed_correct_outcome_does_not_increment_failed_attempts(
    patch_session_local, db_session: AsyncSession
) -> None:
    gap = await _make_gap(db_session)
    chw = _test_chw_id()
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "spice_action_observed",
            "event_id": "evt-spice-ok",
            "chw_id": str(chw),
            "outcome": "correct",
            "payload_json": {
                "kind": "assessment_submitted",
                "behavioural_gap_id": str(gap.id),
            },
        }
    )
    r = await db_session.execute(
        select(CHWBehaviouralGapState).where(
            CHWBehaviouralGapState.chw_id == chw,
            CHWBehaviouralGapState.behavioural_gap_id == gap.id,
        )
    )
    state = r.scalar_one()
    assert state.failed_attempts_count == 0


@pytest.mark.asyncio
@requires_db
async def test_spice_action_observed_missing_behavioural_gap_id_no_row(
    patch_session_local, db_session: AsyncSession
) -> None:
    chw = _test_chw_id()
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "spice_action_observed",
            "event_id": "evt-spice-2",
            "chw_id": str(chw),
            "payload_json": {"kind": "assessment_submitted"},
        }
    )
    r = await db_session.execute(select(CHWBehaviouralGapState))
    assert r.first() is None


@pytest.mark.asyncio
@requires_db
async def test_spice_action_observed_second_event_increments_occurrence_count(
    patch_session_local, db_session: AsyncSession
) -> None:
    gap = await _make_gap(db_session)
    chw = _test_chw_id()
    job = {
        "event_type": "spice_action_observed",
        "chw_id": str(chw),
        "payload_json": {
            "kind": "assessment_submitted",
            "behavioural_gap_id": str(gap.id),
        },
    }
    await module_completion_worker.process_module_event_job({**job, "event_id": "evt-a"})
    await module_completion_worker.process_module_event_job({**job, "event_id": "evt-b"})
    r = await db_session.execute(
        select(CHWBehaviouralGapState).where(
            CHWBehaviouralGapState.chw_id == chw,
            CHWBehaviouralGapState.behavioural_gap_id == gap.id,
        )
    )
    state = r.scalar_one()
    assert state.occurrence_count == 2


# ── quiz attempt happy paths ────────────────────────────────────────────


@pytest.mark.asyncio
@requires_db
async def test_passing_quiz_resets_gap_failures(patch_session_local, db_session: AsyncSession) -> None:
    gap = await _make_gap(db_session)
    module = await _make_module(db_session, primary_gap_id=gap.id)
    chw = _test_chw_id()
    # seed: prior failed attempts so we can verify reset
    db_session.add(
        CHWBehaviouralGapState(
            chw_id=chw,
            behavioural_gap_id=gap.id,
            failed_attempts_count=2,
            escalated_to_supervisor=True,
        )
    )
    await db_session.flush()

    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_quiz_attempted",
            "chw_id": str(chw),
            "module_id": str(module.id),
            "quiz_score_pct": 0.85,
        }
    )

    r = await db_session.execute(select(CHWModuleCompletion))
    assert r.first() is None

    # Gap state reset: failed_attempts_count cleared, no longer escalated
    r = await db_session.execute(
        select(CHWBehaviouralGapState).where(
            CHWBehaviouralGapState.chw_id == chw,
            CHWBehaviouralGapState.behavioural_gap_id == gap.id,
        )
    )
    state = r.scalar_one()
    assert state.failed_attempts_count == 0
    assert state.escalated_to_supervisor is False
    assert state.last_reinforced_at is not None


@pytest.mark.asyncio
@requires_db
async def test_failing_quiz_increments_gap_failed_attempts(
    patch_session_local, db_session: AsyncSession
) -> None:
    gap = await _make_gap(db_session)
    module = await _make_module(db_session, primary_gap_id=gap.id)
    chw = _test_chw_id()
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_quiz_attempted",
            "chw_id": str(chw),
            "module_id": str(module.id),
            "quiz_score_pct": 0.40,
        }
    )
    r = await db_session.execute(
        select(CHWBehaviouralGapState).where(
            CHWBehaviouralGapState.chw_id == chw,
            CHWBehaviouralGapState.behavioural_gap_id == gap.id,
        )
    )
    state = r.scalar_one()
    assert state.failed_attempts_count == 1


@pytest.mark.asyncio
@requires_db
async def test_quiz_outcome_incorrect_increments_failures_even_when_score_passes(
    patch_session_local, db_session: AsyncSession
) -> None:
    gap = await _make_gap(db_session)
    module = await _make_module(db_session, primary_gap_id=gap.id)
    chw = _test_chw_id()
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_quiz_attempted",
            "chw_id": str(chw),
            "module_id": str(module.id),
            "quiz_score_pct": 0.95,
            "outcome": "incorrect",
        }
    )
    r = await db_session.execute(
        select(CHWBehaviouralGapState).where(
            CHWBehaviouralGapState.chw_id == chw,
            CHWBehaviouralGapState.behavioural_gap_id == gap.id,
        )
    )
    state = r.scalar_one()
    assert state.failed_attempts_count == 1


@pytest.mark.asyncio
@requires_db
async def test_quiz_outcome_correct_decrements_failed_attempts(
    patch_session_local, db_session: AsyncSession
) -> None:
    gap = await _make_gap(db_session)
    module = await _make_module(db_session, primary_gap_id=gap.id)
    chw = _test_chw_id()
    db_session.add(
        CHWBehaviouralGapState(
            chw_id=chw,
            behavioural_gap_id=gap.id,
            failed_attempts_count=3,
            escalated_to_supervisor=True,
            status="active",
        )
    )
    await db_session.flush()
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_quiz_attempted",
            "chw_id": str(chw),
            "module_id": str(module.id),
            "quiz_score_pct": 0.20,
            "outcome": "correct",
        }
    )
    r = await db_session.execute(
        select(CHWBehaviouralGapState).where(
            CHWBehaviouralGapState.chw_id == chw,
            CHWBehaviouralGapState.behavioural_gap_id == gap.id,
        )
    )
    state = r.scalar_one()
    assert state.failed_attempts_count == 2
    assert state.escalated_to_supervisor is False
    assert state.status == "active"


@pytest.mark.asyncio
@requires_db
async def test_quiz_outcome_correct_hitting_zero_sets_resolved(
    patch_session_local, db_session: AsyncSession
) -> None:
    gap = await _make_gap(db_session)
    module = await _make_module(db_session, primary_gap_id=gap.id)
    chw = _test_chw_id()
    db_session.add(
        CHWBehaviouralGapState(
            chw_id=chw,
            behavioural_gap_id=gap.id,
            failed_attempts_count=1,
            status="active",
        )
    )
    await db_session.flush()
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_quiz_attempted",
            "chw_id": str(chw),
            "module_id": str(module.id),
            "quiz_score_pct": 0.0,
            "outcome": "correct",
        }
    )
    r = await db_session.execute(
        select(CHWBehaviouralGapState).where(
            CHWBehaviouralGapState.chw_id == chw,
            CHWBehaviouralGapState.behavioural_gap_id == gap.id,
        )
    )
    state = r.scalar_one()
    assert state.failed_attempts_count == 0
    assert state.status == "resolved"


@pytest.mark.asyncio
@requires_db
async def test_three_fails_in_window_escalates_via_gap_state_service(
    patch_session_local, db_session: AsyncSession
) -> None:
    """Verifies we reuse the W-8 escalation rule rather than reimplementing it."""
    gap = await _make_gap(db_session)
    module = await _make_module(db_session, primary_gap_id=gap.id)
    chw = _test_chw_id()
    for _ in range(3):
        await module_completion_worker.process_module_event_job(
            {
                "event_type": "module_quiz_attempted",
                "chw_id": str(chw),
                "module_id": str(module.id),
                "quiz_score_pct": 0.30,
            }
        )
    r = await db_session.execute(
        select(CHWBehaviouralGapState).where(
            CHWBehaviouralGapState.chw_id == chw,
            CHWBehaviouralGapState.behavioural_gap_id == gap.id,
        )
    )
    state = r.scalar_one()
    assert state.failed_attempts_count == 3
    assert state.escalated_to_supervisor is True


@pytest.mark.asyncio
@requires_db
async def test_quiz_event_for_module_without_primary_gap_skips_gap_update(
    patch_session_local, db_session: AsyncSession
) -> None:
    """Modules without a primary_gap_id (broad refreshers) skip quiz-driven
    gap updates and do not write chw_module_completion."""
    module = await _make_module(db_session, primary_gap_id=None)
    chw = _test_chw_id()
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_quiz_attempted",
            "chw_id": str(chw),
            "module_id": str(module.id),
            "quiz_score_pct": 0.90,
        }
    )
    r = await db_session.execute(select(CHWModuleCompletion))
    assert r.first() is None
    r = await db_session.execute(select(CHWBehaviouralGapState))
    assert r.first() is None


@pytest.mark.asyncio
@requires_db
async def test_quiz_event_with_missing_score_treated_as_zero_fail(
    patch_session_local, db_session: AsyncSession
) -> None:
    gap = await _make_gap(db_session)
    module = await _make_module(db_session, primary_gap_id=gap.id)
    chw = _test_chw_id()
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_quiz_attempted",
            "chw_id": str(chw),
            "module_id": str(module.id),
            # quiz_score_pct intentionally omitted
        }
    )
    r = await db_session.execute(select(CHWModuleCompletion))
    assert r.first() is None
    r = await db_session.execute(
        select(CHWBehaviouralGapState).where(
            CHWBehaviouralGapState.chw_id == chw,
            CHWBehaviouralGapState.behavioural_gap_id == gap.id,
        )
    )
    assert r.scalar_one().failed_attempts_count == 1


# ── module_completed event ──────────────────────────────────────────────


@pytest.mark.asyncio
@requires_db
async def test_module_completed_stamps_completion_when_row_exists(
    patch_session_local, db_session: AsyncSession
) -> None:
    module = await _make_module(db_session)
    chw = _test_chw_id()
    db_session.add(
        CHWModuleCompletion(
            chw_id=chw,
            module_family_id=module.module_family_id,
            attempts_since_last_pass=0,
        )
    )
    await db_session.flush()
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_completed",
            "chw_id": str(chw),
            "module_id": str(module.id),
        }
    )
    r = await db_session.execute(select(CHWModuleCompletion).where(CHWModuleCompletion.chw_id == chw))
    comp = r.scalar_one()
    assert comp.completed_at is not None


# ── version resolution ──────────────────────────────────────────────────


@pytest.mark.asyncio
@requires_db
async def test_module_version_attribution_uses_event_module_id(
    patch_session_local, db_session: AsyncSession
) -> None:
    """The event carries the exact module_id (version-specific row) the SDK
    rendered. The worker attributes the completion to that row, not to the
    family's current_published_module_id — important when a CHW completes
    v1 after v2 has been published (they synced before the new version
    landed)."""
    family = ModuleFamily(module_code=f"VER-{uuid4().hex[:8]}")
    db_session.add(family)
    await db_session.flush()
    v1 = Module(
        module_family_id=family.id,
        version=1,
        lifecycle_status="deprecated",
        module_type="refresher",
        title_bn="v1",
        domain="hypertension",
        estimated_minutes=5,
        difficulty_level="basic",
    )
    v2 = Module(
        module_family_id=family.id,
        version=2,
        lifecycle_status="published",
        module_type="refresher",
        title_bn="v2",
        domain="hypertension",
        estimated_minutes=5,
        difficulty_level="basic",
    )
    db_session.add_all([v1, v2])
    await db_session.flush()
    family.current_published_module_id = v2.id
    await db_session.flush()
    chw = _test_chw_id()
    db_session.add(CHWModuleCompletion(chw_id=chw, module_family_id=family.id, attempts_since_last_pass=0))
    await db_session.flush()
    await module_completion_worker.process_module_event_job(
        {
            "event_type": "module_completed",
            "chw_id": str(chw),
            "module_id": str(v1.id),  # CHW was on v1
        }
    )
    r = await db_session.execute(select(CHWModuleCompletion).where(CHWModuleCompletion.chw_id == chw))
    comp = r.scalar_one()
    assert comp.latest_completed_module_id == v1.id  # not v2
