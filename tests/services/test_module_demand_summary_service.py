"""Tests for module demand summary text builder and service."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from mc_contracts.dashboard import (
    DigitalHelpModuleUsageItem,
    DigitalHelpModuleUsageResponse,
)
from platform_service.services.module_demand_summary_service import ModuleDemandSummaryService
from platform_service.services.prompts.module_demand_summary_text import (
    AggregatedCreationDemand,
    build_module_demand_text_summary,
)


def test_build_summary_empty_window() -> None:
    summary = build_module_demand_text_summary(
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
        usage_modules=[],
        creation_demand=[],
    )
    assert "No module usage or creation demand" in summary
    assert "2026-07-01 to 2026-07-31" in summary


def test_build_summary_usage_only() -> None:
    module_id = uuid4()
    summary = build_module_demand_text_summary(
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 1),
        usage_modules=[
            DigitalHelpModuleUsageItem(
                module_id=module_id,
                digital_help_count=7,
                module_requested_count=3,
                title={"en": "Hypertension basics"},
            )
        ],
        creation_demand=[],
    )
    assert "Hypertension basics" in summary
    assert "7 digital-help" in summary
    assert "3 requests" in summary
    assert "Unattributed demand" not in summary


def test_build_summary_creation_only() -> None:
    summary = build_module_demand_text_summary(
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
        usage_modules=[],
        creation_demand=[
            AggregatedCreationDemand(
                suggestion_kind="proposed_topic",
                display_title="Neonatal resuscitation",
                matched_module_id=None,
                question_count=0,
                request_count=5,
                evidence_count=5,
            ),
            AggregatedCreationDemand(
                suggestion_kind="matched_draft",
                display_title="Draft BP module",
                matched_module_id=uuid4(),
                question_count=2,
                request_count=1,
                evidence_count=3,
            ),
        ],
    )
    assert "Create Neonatal resuscitation" in summary
    assert "5 requests" in summary
    assert "Finish draft Draft BP module" in summary
    assert "digital help most on" not in summary


def test_build_summary_both_sections() -> None:
    summary = build_module_demand_text_summary(
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
        usage_modules=[
            DigitalHelpModuleUsageItem(
                module_id=uuid4(),
                digital_help_count=4,
                module_requested_count=0,
                title={"en": "ANC visits"},
            )
        ],
        creation_demand=[
            AggregatedCreationDemand(
                suggestion_kind="proposed_topic",
                display_title="Danger signs",
                matched_module_id=None,
                question_count=4,
                request_count=0,
                evidence_count=4,
            )
        ],
    )
    assert "ANC visits" in summary
    assert "Create Danger signs" in summary


@pytest.mark.asyncio
async def test_get_text_summary_composes_usage_and_creation() -> None:
    ch_mock = MagicMock()
    session = MagicMock()
    module_id = uuid4()
    service = ModuleDemandSummaryService(ch_mock, session)
    service._analytics.get_digital_help_module_usage = AsyncMock(
        return_value=DigitalHelpModuleUsageResponse(
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
            total_digital_help=5,
            total_module_requested=0,
            total_modules=1,
            limit=10,
            offset=0,
            modules=[
                DigitalHelpModuleUsageItem(
                    module_id=module_id,
                    digital_help_count=5,
                    module_requested_count=0,
                    title={"en": "Family planning"},
                )
            ],
        )
    )
    service._fetch_aggregated_creation_demand = AsyncMock(
        return_value=[
            AggregatedCreationDemand(
                suggestion_kind="proposed_topic",
                display_title="Postpartum care",
                matched_module_id=None,
                question_count=0,
                request_count=3,
                evidence_count=3,
            )
        ]
    )

    result = await service.get_text_summary(
        tenant_id=1,
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
        chw_ids=None,
        top_limit=10,
    )

    assert result.from_date == date(2026, 7, 1)
    assert result.to_date == date(2026, 7, 31)
    assert "Family planning" in result.summary
    assert "Postpartum care" in result.summary


@pytest.mark.asyncio
async def test_get_text_summary_empty_chw_ids() -> None:
    ch_mock = MagicMock()
    session = MagicMock()
    service = ModuleDemandSummaryService(ch_mock, session)
    service._analytics.get_digital_help_module_usage = AsyncMock(
        return_value=DigitalHelpModuleUsageResponse(
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
            total_digital_help=0,
            total_module_requested=0,
            total_modules=0,
            limit=10,
            offset=0,
            modules=[],
        )
    )
    service._suggestion_repo.list_all_in_range = AsyncMock(return_value=[])

    result = await service.get_text_summary(
        tenant_id=1,
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
        chw_ids=frozenset(),
        top_limit=10,
    )

    assert "No module usage or creation demand" in result.summary
    service._suggestion_repo.list_all_in_range.assert_awaited_once_with(
        tenant_id=1,
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
        visible_chw_ids=frozenset(),
    )


@pytest.mark.asyncio
async def test_aggregates_multi_day_suggestions_by_topic() -> None:
    ch_mock = MagicMock()
    session = MagicMock()
    service = ModuleDemandSummaryService(ch_mock, session)
    now = datetime(2026, 7, 30, 4, 0, tzinfo=UTC)
    row_day_one = MagicMock(
        id=uuid4(),
        suggestion_date=date(2026, 7, 28),
        suggestion_kind="proposed_topic",
        matched_module_id=None,
        proposed_topic="Danger signs",
        display_title="Danger signs",
        rationale="why",
        question_count=2,
        request_count=1,
        evidence_count=3,
        rank=1,
        computed_at=now,
        evidence=[],
    )
    row_day_two = MagicMock(
        id=uuid4(),
        suggestion_date=date(2026, 7, 29),
        suggestion_kind="proposed_topic",
        matched_module_id=None,
        proposed_topic="Danger signs",
        display_title="Danger signs",
        rationale="why",
        question_count=1,
        request_count=2,
        evidence_count=3,
        rank=1,
        computed_at=now,
        evidence=[],
    )
    service._suggestion_repo.list_all_in_range = AsyncMock(return_value=[row_day_one, row_day_two])

    aggregated = await service._fetch_aggregated_creation_demand(
        tenant_id=1,
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
        chw_ids=None,
        top_limit=10,
    )

    assert len(aggregated) == 1
    assert aggregated[0].display_title == "Danger signs"
    assert aggregated[0].question_count == 3
    assert aggregated[0].request_count == 3
    assert aggregated[0].evidence_count == 6
