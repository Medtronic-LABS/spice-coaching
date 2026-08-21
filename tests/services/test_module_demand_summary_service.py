"""Tests for module demand summary builder and service."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from mc_contracts.dashboard import (
    DigitalHelpModuleUsageItem,
    DigitalHelpModuleUsageResponse,
)
from platform_service.services.module_demand_summary_service import ModuleDemandSummaryService
from platform_service.services.prompts.module_demand_summary_text import (
    _EN_DASH,
    _format_date_range,
    build_module_demand_summary,
)

_SCREENSHOT_NARRATIVE = (
    "Most demand can be addressed with existing or draft content. "
    "Prioritize assigning high-demand published modules, publish matching drafts "
    "to close immediate gaps, and create new content only for topics with no existing coverage."
)


def _suggestion_row(
    *,
    suggestion_kind: str,
    question_count: int,
    request_count: int,
    evidence_count: int | None = None,
    display_title: str = "Topic",
    proposed_topic: str | None = None,
    matched_module_id: UUID | None = None,
) -> MagicMock:
    now = datetime(2026, 7, 30, 4, 0, tzinfo=UTC)
    return MagicMock(
        id=uuid4(),
        suggestion_date=date(2026, 7, 28),
        suggestion_kind=suggestion_kind,
        matched_module_id=matched_module_id,
        proposed_topic=proposed_topic or display_title,
        display_title=display_title,
        rationale="why",
        question_count=question_count,
        request_count=request_count,
        evidence_count=evidence_count if evidence_count is not None else question_count + request_count,
        rank=1,
        computed_at=now,
        evidence=[],
    )


def test_build_summary_empty_window() -> None:
    result = build_module_demand_summary(
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
        assign_volume=0,
        publish_volume=0,
        create_volume=0,
    )
    assert result.title == "Insights from Module Usage"
    assert result.date_label == f"Jul 1{_EN_DASH}31, 2026"
    assert result.narrative is None
    assert result.empty_message == f"No module demand for your team in Jul 1{_EN_DASH}31, 2026."
    assert result.demand_pattern == []


def test_format_date_range_variants() -> None:
    assert _format_date_range(date(2026, 8, 1), date(2026, 8, 1)) == "Aug 1, 2026"
    assert _format_date_range(date(2026, 8, 1), date(2026, 8, 17)) == f"Aug 1{_EN_DASH}17, 2026"
    assert _format_date_range(date(2026, 8, 1), date(2026, 9, 3)) == f"Aug 1{_EN_DASH}Sep 3, 2026"
    assert _format_date_range(date(2025, 12, 20), date(2026, 1, 5)) == (f"Dec 20, 2025{_EN_DASH}Jan 5, 2026")


def test_build_summary_assign_only() -> None:
    result = build_module_demand_summary(
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 1),
        assign_volume=10,
        publish_volume=0,
        create_volume=0,
    )
    assert result.title == "Insights from Module Usage"
    assert result.date_label == "Jul 1, 2026"
    assert result.empty_message is None
    assert result.narrative == (
        "Most demand can be addressed with existing published modules. "
        "Prioritize assigning high-demand published modules."
    )
    assert len(result.demand_pattern) == 1
    assert result.demand_pattern[0].bucket == "assign"
    assert result.demand_pattern[0].title == "Existing coverage"
    assert result.demand_pattern[0].description == ("Demand is concentrated around a few published modules")


def test_build_summary_publish_only() -> None:
    result = build_module_demand_summary(
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 17),
        assign_volume=0,
        publish_volume=4,
        create_volume=0,
    )
    assert result.date_label == f"Aug 1{_EN_DASH}17, 2026"
    assert result.narrative == (
        "Most demand can be addressed with draft content ready to publish. "
        "Prioritize publishing matching drafts to close immediate gaps."
    )
    assert len(result.demand_pattern) == 1
    assert result.demand_pattern[0].bucket == "publish"
    assert result.demand_pattern[0].title == "Ready to publish"
    assert result.demand_pattern[0].description == ("Some unanswered demand already has draft content")


def test_build_summary_create_only() -> None:
    result = build_module_demand_summary(
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
        assign_volume=0,
        publish_volume=0,
        create_volume=5,
    )
    assert result.narrative == (
        "Most demand represents opportunities for new modules. "
        "Prioritize creating new content only for topics with no existing coverage."
    )
    assert len(result.demand_pattern) == 1
    assert result.demand_pattern[0].bucket == "create"
    assert result.demand_pattern[0].title == "Content gaps"
    assert result.demand_pattern[0].description == (
        "Remaining demand represents opportunities for new modules"
    )


def test_build_summary_all_three_assign_highest_uses_screenshot_copy() -> None:
    result = build_module_demand_summary(
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 17),
        assign_volume=20,
        publish_volume=8,
        create_volume=3,
    )
    assert result.narrative == _SCREENSHOT_NARRATIVE
    assert [item.bucket for item in result.demand_pattern] == ["assign", "publish", "create"]
    assert result.demand_pattern[0].title == "Existing coverage"
    assert result.demand_pattern[1].title == "Ready to publish"
    assert result.demand_pattern[2].title == "Content gaps"


def test_build_summary_all_three_create_highest() -> None:
    result = build_module_demand_summary(
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 17),
        assign_volume=5,
        publish_volume=8,
        create_volume=20,
    )
    assert result.narrative == (
        "Most demand represents opportunities for new modules. "
        "Prioritize creating new modules for uncovered topics, "
        "publishing matching drafts to close immediate gaps, "
        "and assigning high-demand published modules."
    )
    assert [item.bucket for item in result.demand_pattern] == ["create", "publish", "assign"]
    assert result.demand_pattern[0].title == "Content gaps"
    assert result.demand_pattern[1].title == "Ready to publish"
    assert result.demand_pattern[2].title == "Existing coverage"


def test_build_summary_tie_assign_equals_publish_breaks_assign_first() -> None:
    result = build_module_demand_summary(
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 17),
        assign_volume=10,
        publish_volume=10,
        create_volume=3,
    )
    assert [item.bucket for item in result.demand_pattern] == ["assign", "publish", "create"]
    assert result.narrative == _SCREENSHOT_NARRATIVE


def test_build_summary_tie_assign_equals_create_without_publish() -> None:
    result = build_module_demand_summary(
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 17),
        assign_volume=10,
        publish_volume=0,
        create_volume=10,
    )
    assert result.narrative == (
        "Most demand can be addressed with existing published modules. "
        "Prioritize assigning high-demand published modules and "
        "creating new content only for topics with no existing coverage."
    )
    assert [item.bucket for item in result.demand_pattern] == ["assign", "create"]
    assert result.demand_pattern[0].title == "Existing coverage"
    assert result.demand_pattern[1].title == "Content gaps"


@pytest.mark.asyncio
async def test_get_summary_uses_full_usage_totals() -> None:
    ch_mock = MagicMock()
    session = MagicMock()
    module_id = uuid4()
    service = ModuleDemandSummaryService(ch_mock, session)
    service._analytics.get_digital_help_module_usage = AsyncMock(
        return_value=DigitalHelpModuleUsageResponse(
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
            total_digital_help=50,
            total_module_requested=10,
            total_modules=12,
            limit=1,
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
    service._creation_volumes = AsyncMock(return_value=(4, 3))

    result = await service.get_summary(
        tenant_id=1,
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
        chw_ids=None,
        top_limit=5,
    )

    assert result.from_date == date(2026, 7, 1)
    assert result.to_date == date(2026, 7, 31)
    assert result.narrative == _SCREENSHOT_NARRATIVE
    assert result.empty_message is None
    service._analytics.get_digital_help_module_usage.assert_awaited_once()
    assert service._analytics.get_digital_help_module_usage.await_args.kwargs["limit"] == 1


@pytest.mark.asyncio
async def test_get_summary_empty_chw_ids() -> None:
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
            limit=1,
            offset=0,
            modules=[],
        )
    )
    service._suggestion_repo.list_all_in_range = AsyncMock(return_value=[])

    result = await service.get_summary(
        tenant_id=1,
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
        chw_ids=frozenset(),
        top_limit=10,
    )

    assert result.empty_message == f"No module demand for your team in Jul 1{_EN_DASH}31, 2026."
    assert result.narrative is None
    assert result.demand_pattern == []
    service._suggestion_repo.list_all_in_range.assert_awaited_once_with(
        tenant_id=1,
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
        visible_chw_ids=frozenset(),
    )


@pytest.mark.asyncio
async def test_creation_volumes_sums_all_rows_by_kind() -> None:
    ch_mock = MagicMock()
    session = MagicMock()
    service = ModuleDemandSummaryService(ch_mock, session)
    service._suggestion_repo.list_all_in_range = AsyncMock(
        return_value=[
            _suggestion_row(
                suggestion_kind="proposed_topic",
                display_title="Danger signs",
                question_count=2,
                request_count=1,
            ),
            _suggestion_row(
                suggestion_kind="proposed_topic",
                display_title="Danger signs",
                question_count=1,
                request_count=2,
            ),
            _suggestion_row(
                suggestion_kind="matched_draft",
                display_title="Draft BP module",
                matched_module_id=uuid4(),
                question_count=2,
                request_count=1,
            ),
            _suggestion_row(
                suggestion_kind="proposed_topic",
                display_title="Empty",
                question_count=0,
                request_count=0,
                evidence_count=0,
            ),
        ]
    )

    publish_volume, create_volume = await service._creation_volumes(
        tenant_id=1,
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
        chw_ids=None,
    )

    assert publish_volume == 3
    assert create_volume == 6
