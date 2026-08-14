"""Service/worker tests for module creation suggestions refresh."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from platform_service.services.module_creation_suggestion_classifier import (
    SUGGESTION_KIND_PROPOSED_TOPIC,
    ClassifiedSuggestion,
)
from platform_service.services.module_creation_suggestion_service import (
    ModuleCreationSuggestionService,
)
from platform_service.services.unattributed_demand_aggregator import DedupedEvidence


@pytest.mark.asyncio
async def test_refresh_skips_write_when_no_evidence() -> None:
    session = MagicMock()
    session.commit = AsyncMock()
    service = ModuleCreationSuggestionService(
        session,
        client=MagicMock(),
        settings=MagicMock(
            module_creation_suggestions_llm_timeout_seconds=60.0,
            module_creation_suggestions_max_suggestions=20,
            module_creation_suggestions_max_evidence=80,
        ),
        ch_client=MagicMock(),
    )
    service._aggregator.fetch_for_day = AsyncMock(return_value=([], []))
    service._repo.replace_for_day = AsyncMock()

    count = await service.refresh_for_day(tenant_id=1, suggestion_date=date(2026, 7, 29))
    assert count == 0
    service._repo.replace_for_day.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_replaces_after_successful_classify() -> None:
    session = MagicMock()
    session.commit = AsyncMock()
    settings = MagicMock(
        module_creation_suggestions_llm_timeout_seconds=60.0,
        module_creation_suggestions_max_suggestions=20,
        module_creation_suggestions_max_evidence=80,
    )
    service = ModuleCreationSuggestionService(
        session,
        client=MagicMock(),
        settings=settings,
        ch_client=MagicMock(),
    )
    question = DedupedEvidence(
        source="digital_help",
        text="Danger signs?",
        normalized_text="danger signs?",
        occurrence_count=4,
        last_seen_at=datetime(2026, 7, 29, 12, 0, tzinfo=UTC),
        sample_event_id="e1",
        sample_chw_id=9,
    )
    service._aggregator.fetch_for_day = AsyncMock(return_value=([question], []))
    service._load_drafts = AsyncMock(return_value=[])
    service._classifier.classify = AsyncMock(
        return_value=[
            ClassifiedSuggestion(
                suggestion_kind=SUGGESTION_KIND_PROPOSED_TOPIC,
                matched_module_id=None,
                proposed_topic="Danger signs",
                display_title="Danger signs",
                rationale="Frequent unattributed questions",
                question_keys=["danger signs?"],
                request_keys=[],
            )
        ]
    )
    service._repo.replace_for_day = AsyncMock(return_value=[])

    count = await service.refresh_for_day(tenant_id=1, suggestion_date=date(2026, 7, 29))
    assert count == 1
    service._repo.replace_for_day.assert_awaited_once()
    kwargs = service._repo.replace_for_day.await_args.kwargs
    assert kwargs["suggestion_date"] == date(2026, 7, 29)
    assert len(kwargs["rows"]) == 1
    assert kwargs["rows"][0].display_title == "Danger signs"
    assert kwargs["rows"][0].rank == 1
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_does_not_replace_when_llm_fails() -> None:
    session = MagicMock()
    session.commit = AsyncMock()
    settings = MagicMock(
        module_creation_suggestions_llm_timeout_seconds=60.0,
        module_creation_suggestions_max_suggestions=20,
        module_creation_suggestions_max_evidence=80,
    )
    service = ModuleCreationSuggestionService(
        session,
        client=MagicMock(),
        settings=settings,
        ch_client=MagicMock(),
    )
    service._aggregator.fetch_for_day = AsyncMock(
        return_value=[
            (
                [
                    DedupedEvidence(
                        source="digital_help",
                        text="Q",
                        normalized_text="q",
                        occurrence_count=1,
                        last_seen_at=None,
                        sample_event_id=None,
                        sample_chw_id=None,
                    )
                ],
                [],
            )
        ][0]
    )
    service._load_drafts = AsyncMock(return_value=[])
    service._classifier.classify = AsyncMock(side_effect=RuntimeError("ai-runtime error: boom"))
    service._repo.replace_for_day = AsyncMock()

    with pytest.raises(RuntimeError, match="ai-runtime error"):
        await service.refresh_for_day(tenant_id=1, suggestion_date=date(2026, 7, 29))

    service._repo.replace_for_day.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_worker_processes_scopes() -> None:
    from platform_service.workers.module_creation_suggestions_worker import (
        refresh_module_creation_suggestions_job,
    )

    service = MagicMock()
    service.list_scopes = AsyncMock(return_value=[None, uuid4()])
    service.refresh_for_day = AsyncMock(side_effect=[2, 0])

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    session_cm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "platform_service.workers.module_creation_suggestions_worker.SessionLocal",
            return_value=session_cm,
        ),
        patch(
            "platform_service.workers.module_creation_suggestions_worker.ModuleCreationSuggestionService",
            return_value=service,
        ),
    ):
        result = await refresh_module_creation_suggestions_job()

    assert result["scopes_updated"] == 2
    assert result["suggestions_written"] == 2
    assert service.refresh_for_day.await_count == 2


@pytest.mark.asyncio
async def test_list_suggestions_recomputes_counts_for_visible_chws() -> None:
    suggestion_id = uuid4()
    now = datetime(2026, 7, 30, 4, 0, tzinfo=UTC)
    in_scope = MagicMock(
        source="digital_help",
        text="In scope",
        normalized_text="in scope",
        occurrence_count=3,
        last_seen_at=now,
        sample_chw_id=3001,
    )
    out_of_scope = MagicMock(
        source="module_requested",
        text="Out",
        normalized_text="out",
        occurrence_count=5,
        last_seen_at=now,
        sample_chw_id=9999,
    )
    null_chw = MagicMock(
        source="digital_help",
        text="Null",
        normalized_text="null",
        occurrence_count=2,
        last_seen_at=now,
        sample_chw_id=None,
    )
    row = MagicMock(
        id=suggestion_id,
        suggestion_date=date(2026, 7, 29),
        suggestion_kind="proposed_topic",
        matched_module_id=None,
        proposed_topic="Topic",
        display_title="Topic",
        rationale="why",
        question_count=5,
        request_count=5,
        evidence_count=10,
        rank=1,
        computed_at=now,
        evidence=[in_scope, out_of_scope, null_chw],
    )
    session = MagicMock()
    service = ModuleCreationSuggestionService(
        session,
        client=MagicMock(),
        settings=MagicMock(),
        ch_client=MagicMock(),
    )
    service._repo.list_in_range = AsyncMock(return_value=([row], 1))

    result = await service.list_suggestions(
        tenant_id=1,
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
        visible_chw_ids=frozenset({3001}),
    )

    assert result.total_suggestions == 1
    item = result.suggestions[0]
    assert item.question_count == 3
    assert item.request_count == 0
    assert item.evidence_count == 3
    assert item.rank == 1
    service._repo.list_in_range.assert_awaited_once()
    assert service._repo.list_in_range.await_args.kwargs["visible_chw_ids"] == frozenset({3001})


@pytest.mark.asyncio
async def test_get_detail_filters_evidence_and_404s_when_none_in_scope() -> None:
    suggestion_id = uuid4()
    now = datetime(2026, 7, 30, 4, 0, tzinfo=UTC)
    out_only = MagicMock(
        source="digital_help",
        text="Out",
        normalized_text="out",
        occurrence_count=2,
        last_seen_at=now,
        sample_chw_id=9999,
    )
    row = MagicMock(
        id=suggestion_id,
        suggestion_date=date(2026, 7, 29),
        suggestion_kind="proposed_topic",
        matched_module_id=None,
        proposed_topic="Topic",
        display_title="Topic",
        rationale="why",
        question_count=2,
        request_count=0,
        evidence_count=2,
        rank=1,
        computed_at=now,
        evidence=[out_only],
    )
    session = MagicMock()
    service = ModuleCreationSuggestionService(
        session,
        client=MagicMock(),
        settings=MagicMock(),
        ch_client=MagicMock(),
    )
    service._repo.get_detail = AsyncMock(return_value=row)

    with pytest.raises(LookupError, match="suggestion not found"):
        await service.get_detail(
            suggestion_id=suggestion_id,
            tenant_id=1,
            visible_chw_ids=frozenset({3001}),
        )


@pytest.mark.asyncio
async def test_get_detail_returns_scoped_evidence() -> None:
    suggestion_id = uuid4()
    now = datetime(2026, 7, 30, 4, 0, tzinfo=UTC)
    in_scope_q = MagicMock(
        source="digital_help",
        text="Q",
        normalized_text="q",
        occurrence_count=2,
        last_seen_at=now,
        sample_chw_id=3001,
    )
    in_scope_r = MagicMock(
        source="module_requested",
        text="R",
        normalized_text="r",
        occurrence_count=1,
        last_seen_at=now,
        sample_chw_id=3001,
    )
    out_of_scope = MagicMock(
        source="digital_help",
        text="Peer",
        normalized_text="peer",
        occurrence_count=9,
        last_seen_at=now,
        sample_chw_id=9999,
    )
    row = MagicMock(
        id=suggestion_id,
        suggestion_date=date(2026, 7, 29),
        suggestion_kind="proposed_topic",
        matched_module_id=None,
        proposed_topic="Topic",
        display_title="Topic",
        rationale="why",
        question_count=11,
        request_count=1,
        evidence_count=12,
        rank=2,
        computed_at=now,
        evidence=[in_scope_q, in_scope_r, out_of_scope],
    )
    session = MagicMock()
    service = ModuleCreationSuggestionService(
        session,
        client=MagicMock(),
        settings=MagicMock(),
        ch_client=MagicMock(),
    )
    service._repo.get_detail = AsyncMock(return_value=row)

    org_user = MagicMock()
    org_user.name = "SK One"
    org_user.role = "SHASTIYA_KORMI"
    org_user.division = "D"
    org_user.district = "Dist"
    org_user.upazila_names = frozenset({"Up"})
    with patch(
        "platform_service.services.module_creation_suggestion_service.org_user_index",
        new_callable=AsyncMock,
        return_value={3001: org_user},
    ):
        result = await service.get_detail(
            suggestion_id=suggestion_id,
            tenant_id=1,
            visible_chw_ids=frozenset({3001}),
        )

    assert len(result.questions) == 1
    assert len(result.requests) == 1
    assert result.questions[0].prompted_by.user_id == 3001
    assert result.questions[0].prompted_by.user_name == "SK One"
    assert result.requests[0].prompted_by.user_id == 3001
    assert result.suggestion.question_count == 2
    assert result.suggestion.request_count == 1
    assert result.suggestion.evidence_count == 3
    assert result.suggestion.rank == 2
