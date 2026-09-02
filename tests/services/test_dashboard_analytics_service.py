"""Unit tests for DashboardAnalyticsService."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from platform_service.db.repositories.module_repository import ModuleRepository
from platform_service.services.dashboard_analytics_service import DashboardAnalyticsService


@pytest.mark.asyncio
async def test_get_digital_help_module_usage_ranks_by_combined_count() -> None:
    """Combined rank: 3+8 (=11) beats 10+0; request-only module is included."""
    module_combined = uuid4()
    module_chat_only = uuid4()
    module_request_only = uuid4()
    family_combined = uuid4()
    family_chat = uuid4()
    ch_mock = MagicMock()
    ch_mock.query_rows = AsyncMock(
        return_value=[
            {
                "module_id": str(module_combined),
                "digital_help_count": 3,
                "module_requested_count": 8,
            },
            {
                "module_id": str(module_chat_only),
                "digital_help_count": 10,
                "module_requested_count": 0,
            },
            {
                "module_id": str(module_request_only),
                "digital_help_count": 0,
                "module_requested_count": 5,
            },
        ]
    )
    session = MagicMock()
    combined_mod = MagicMock(
        id=module_combined,
        module_family_id=family_combined,
        title_localized={"bn": "Combined BN", "en": "Combined EN"},
    )
    chat_mod = MagicMock(
        id=module_chat_only,
        module_family_id=family_chat,
        title_localized={"bn": "Chat BN"},
    )

    with patch.object(ModuleRepository, "list_modules_by_ids", new_callable=AsyncMock) as mock_by_ids:
        mock_by_ids.return_value = [combined_mod, chat_mod]
        result = await DashboardAnalyticsService(ch_mock, session).get_digital_help_module_usage(
            tenant_id=None,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            limit=20,
        )

    assert result.from_date == date(2026, 1, 1)
    assert result.to_date == date(2026, 1, 31)
    assert result.total_digital_help == 13
    assert result.total_module_requested == 13
    assert result.total_modules == 3
    assert result.limit == 20
    assert result.offset == 0
    assert len(result.modules) == 3
    assert result.modules[0].module_id == module_combined
    assert result.modules[0].module_family_id == family_combined
    assert result.modules[0].digital_help_count == 3
    assert result.modules[0].module_requested_count == 8
    assert result.modules[0].title == {"bn": "Combined BN", "en": "Combined EN"}
    assert result.modules[1].module_id == module_chat_only
    assert result.modules[1].digital_help_count == 10
    assert result.modules[1].module_requested_count == 0
    assert result.modules[2].module_id == module_request_only
    assert result.modules[2].digital_help_count == 0
    assert result.modules[2].module_requested_count == 5


@pytest.mark.asyncio
async def test_get_digital_help_module_usage_empty_window() -> None:
    ch_mock = MagicMock()
    ch_mock.query_rows = AsyncMock(return_value=[])

    result = await DashboardAnalyticsService(ch_mock, None).get_digital_help_module_usage(
        tenant_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 7),
        limit=20,
    )

    assert result.total_digital_help == 0
    assert result.total_module_requested == 0
    assert result.total_modules == 0
    assert result.modules == []


@pytest.mark.asyncio
async def test_get_digital_help_module_usage_passes_tenant_id_to_clickhouse() -> None:
    tenant_id = 1
    ch_mock = MagicMock()
    ch_mock.query_rows = AsyncMock(return_value=[])

    await DashboardAnalyticsService(ch_mock, None).get_digital_help_module_usage(
        tenant_id=tenant_id,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 14),
        limit=5,
    )

    assert len(ch_mock.query_rows.await_args_list) == 1
    call = ch_mock.query_rows.await_args_list[0]
    assert call.kwargs["parameters"]["tenant_id"] == tenant_id
    assert call.kwargs["parameters"]["from_date"] == date(2026, 1, 1)
    assert call.kwargs["parameters"]["to_date"] == date(2026, 1, 14)
    assert call.kwargs["parameters"]["digital_help"] == "digital_help_used"
    assert call.kwargs["parameters"]["module_requested"] == "module_requested"


@pytest.mark.asyncio
async def test_get_digital_help_module_usage_ignores_null_module_id_rows() -> None:
    """Family-only / free-text events (module_id NULL) must not appear in the ranking."""
    module_id = uuid4()
    family_id = uuid4()
    ch_mock = MagicMock()
    # ClickHouse query already filters module_id IS NOT NULL; service also skips None.
    ch_mock.query_rows = AsyncMock(
        return_value=[
            {
                "module_id": str(module_id),
                "digital_help_count": 5,
                "module_requested_count": 2,
            },
            {
                "module_id": None,
                "digital_help_count": 99,
                "module_requested_count": 50,
            },
        ]
    )
    session = MagicMock()
    module_row = MagicMock(
        id=module_id,
        module_family_id=family_id,
        title_localized={"bn": "Only BN", "en": "Only EN"},
    )

    with patch.object(ModuleRepository, "list_modules_by_ids", new_callable=AsyncMock) as mock_by_ids:
        mock_by_ids.return_value = [module_row]
        result = await DashboardAnalyticsService(ch_mock, session).get_digital_help_module_usage(
            tenant_id=None,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            limit=20,
        )

    assert result.total_digital_help == 5
    assert result.total_module_requested == 2
    assert len(result.modules) == 1
    assert result.modules[0].module_id == module_id
    assert result.modules[0].module_family_id == family_id
    assert result.modules[0].digital_help_count == 5
    assert result.modules[0].module_requested_count == 2


@pytest.mark.asyncio
async def test_get_digital_help_module_usage_paginates_modules() -> None:
    modules = [uuid4() for _ in range(3)]
    ch_mock = MagicMock()
    ch_mock.query_rows = AsyncMock(
        return_value=[
            {
                "module_id": str(modules[0]),
                "digital_help_count": 20,
                "module_requested_count": 10,
            },
            {
                "module_id": str(modules[1]),
                "digital_help_count": 15,
                "module_requested_count": 5,
            },
            {
                "module_id": str(modules[2]),
                "digital_help_count": 10,
                "module_requested_count": 0,
            },
        ]
    )
    session = MagicMock()

    with patch.object(ModuleRepository, "list_modules_by_ids", new_callable=AsyncMock) as mock_by_ids:
        mock_by_ids.return_value = []
        result = await DashboardAnalyticsService(ch_mock, session).get_digital_help_module_usage(
            tenant_id=None,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            limit=1,
            offset=1,
        )

    assert result.total_modules == 3
    assert result.total_digital_help == 45
    assert result.total_module_requested == 15
    assert result.limit == 1
    assert result.offset == 1
    assert len(result.modules) == 1
    assert result.modules[0].module_id == modules[1]
    assert result.modules[0].digital_help_count == 15
    assert result.modules[0].module_requested_count == 5


@pytest.mark.asyncio
async def test_get_digital_help_module_questions_paginates_and_skips_blank() -> None:
    module_id = uuid4()
    last_asked = datetime(2026, 1, 15, 12, 0)
    ch_mock = MagicMock()

    async def _query_rows(query: str, parameters: dict | None = None) -> list[dict]:
        if "total_questions" in query:
            return [{"total_questions": 2}]
        return [
            {
                "question": "How to treat fever?",
                "occurrence_count": 3,
                "last_asked_at": last_asked,
                "sample_chw_id": 3001,
            },
            {
                "question": "  ",
                "occurrence_count": 1,
                "last_asked_at": datetime(2026, 1, 10),
                "sample_chw_id": 3002,
            },
        ]

    ch_mock.query_rows = AsyncMock(side_effect=_query_rows)
    session = MagicMock()
    module_row = MagicMock(id=module_id, title_localized={"bn": "Fever BN", "en": "Fever EN"})
    org_user = MagicMock()
    org_user.name = "SK One"
    org_user.role = "SHASTIYA_KORMI"
    org_user.division = "D"
    org_user.district = "Dist"
    org_user.upazila_names = frozenset({"Up"})

    with (
        patch.object(ModuleRepository, "list_modules_by_ids", new_callable=AsyncMock) as mock_by_ids,
        patch(
            "platform_service.services.dashboard_analytics_service.org_user_index",
            new_callable=AsyncMock,
            return_value={3001: org_user},
        ),
    ):
        mock_by_ids.return_value = [module_row]
        result = await DashboardAnalyticsService(ch_mock, session).get_digital_help_module_questions(
            module_id=module_id,
            tenant_id=None,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            limit=50,
            offset=0,
        )

    assert result.module_id == module_id
    assert result.title == {"bn": "Fever BN", "en": "Fever EN"}
    assert result.total_questions == 2
    assert result.total_pages == 1
    assert len(result.questions) == 1
    assert result.questions[0].question == "How to treat fever?"
    assert result.questions[0].occurrence_count == 3
    assert result.questions[0].last_asked_at == last_asked
    assert result.questions[0].asked_by.user_id == 3001
    assert result.questions[0].asked_by.user_name == "SK One"
    assert result.questions[0].asked_by.user_role == "SHASTIYA_KORMI"
    assert ch_mock.query_rows.await_count == 2
    page_call = ch_mock.query_rows.await_args_list[1]
    assert page_call.kwargs["parameters"]["module_id"] == module_id
    assert page_call.kwargs["parameters"]["event_type"] == "digital_help_used"
    assert "module_id = {module_id:UUID}" in page_call.args[0]
    assert "max(timestamp_local) AS last_asked_at" in page_call.args[0]
    assert "argMax(raw_question, timestamp_local)" in page_call.args[0]
    assert "ORDER BY max(timestamp_utc) DESC" in page_call.args[0]


@pytest.mark.asyncio
async def test_get_digital_help_module_questions_empty_window() -> None:
    module_id = uuid4()
    ch_mock = MagicMock()

    async def _query_rows(query: str, parameters: dict | None = None) -> list[dict]:
        if "total_questions" in query:
            return [{"total_questions": 0}]
        return []

    ch_mock.query_rows = AsyncMock(side_effect=_query_rows)

    result = await DashboardAnalyticsService(ch_mock, None).get_digital_help_module_questions(
        module_id=module_id,
        tenant_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 7),
        limit=50,
        offset=0,
    )

    assert result.title is None
    assert result.total_questions == 0
    assert result.total_pages == 0
    assert result.questions == []


@pytest.mark.asyncio
async def test_get_digital_help_module_questions_passes_tenant_id() -> None:
    module_id = uuid4()
    tenant_id = 1
    ch_mock = MagicMock()

    async def _query_rows(query: str, parameters: dict | None = None) -> list[dict]:
        if "total_questions" in query:
            return [{"total_questions": 0}]
        return []

    ch_mock.query_rows = AsyncMock(side_effect=_query_rows)

    await DashboardAnalyticsService(ch_mock, None).get_digital_help_module_questions(
        module_id=module_id,
        tenant_id=tenant_id,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 14),
        limit=10,
        offset=5,
    )

    for call in ch_mock.query_rows.await_args_list:
        assert call.kwargs["parameters"]["tenant_id"] == tenant_id
        assert "tenant_id = {tenant_id:Int64}" in call.args[0]


@pytest.mark.asyncio
async def test_get_digital_help_module_requests_returns_paginated_rows() -> None:
    module_id = uuid4()
    requested_at = datetime(2026, 1, 15, 12, 0)
    ch_mock = MagicMock()

    async def _query_rows(query: str, parameters: dict | None = None) -> list[dict]:
        if "total_requests" in query:
            return [{"total_requests": 2}]
        return [
            {
                "chw_id": 3001,
                "requested_at": requested_at,
                "reason": "Need refresher",
            },
            {
                "chw_id": 3002,
                "requested_at": datetime(2026, 1, 10),
                "reason": "",
            },
        ]

    ch_mock.query_rows = AsyncMock(side_effect=_query_rows)
    session = MagicMock()
    module_row = MagicMock(id=module_id, title_localized={"bn": "Req BN"})
    org_user = MagicMock()
    org_user.name = "SK One"
    org_user.role = "SHASTIYA_KORMI"
    org_user.division = "D"
    org_user.district = "Dist"
    org_user.upazila_names = frozenset({"Up"})

    with (
        patch.object(ModuleRepository, "list_modules_by_ids", new_callable=AsyncMock) as mock_by_ids,
        patch(
            "platform_service.services.dashboard_analytics_service.org_user_index",
            new_callable=AsyncMock,
            return_value={3001: org_user},
        ),
    ):
        mock_by_ids.return_value = [module_row]
        result = await DashboardAnalyticsService(ch_mock, session).get_digital_help_module_requests(
            module_id=module_id,
            tenant_id=None,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            limit=50,
            offset=0,
        )

    assert result.module_id == module_id
    assert result.total_requests == 2
    assert result.total_pages == 1
    assert len(result.requests) == 2
    assert result.requests[0].requested_at == requested_at
    assert result.requests[0].reason == "Need refresher"
    assert result.requests[0].requested_by.user_id == 3001
    assert result.requests[0].requested_by.user_name == "SK One"
    assert result.title == {"bn": "Req BN"}
    page_call = ch_mock.query_rows.await_args_list[1]
    assert page_call.kwargs["parameters"]["module_id"] == module_id
    assert page_call.kwargs["parameters"]["event_type"] == "module_requested"
    assert "module_id = {module_id:UUID}" in page_call.args[0]
    assert "timestamp_local AS requested_at" in page_call.args[0]
    assert "ORDER BY timestamp_utc DESC" in page_call.args[0]


@pytest.mark.asyncio
async def test_get_digital_help_module_requests_zero_when_empty() -> None:
    module_id = uuid4()
    ch_mock = MagicMock()
    ch_mock.query_rows = AsyncMock(return_value=[])

    result = await DashboardAnalyticsService(ch_mock, None).get_digital_help_module_requests(
        module_id=module_id,
        tenant_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 7),
    )

    assert result.total_requests == 0
    assert result.total_pages == 0
    assert result.requests == []
    assert result.title is None


@pytest.mark.asyncio
async def test_get_digital_help_module_requests_passes_tenant_id() -> None:
    module_id = uuid4()
    tenant_id = 1
    ch_mock = MagicMock()
    ch_mock.query_rows = AsyncMock(return_value=[{"total_requests": 0}])

    await DashboardAnalyticsService(ch_mock, None).get_digital_help_module_requests(
        module_id=module_id,
        tenant_id=tenant_id,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 14),
    )

    call = ch_mock.query_rows.await_args_list[0]
    assert call.kwargs["parameters"]["tenant_id"] == tenant_id
    assert "tenant_id = {tenant_id:Int64}" in call.args[0]


@pytest.mark.asyncio
async def test_get_digital_help_module_usage_passes_chw_ids() -> None:
    ch_mock = MagicMock()
    ch_mock.query_rows = AsyncMock(return_value=[])

    await DashboardAnalyticsService(ch_mock, None).get_digital_help_module_usage(
        tenant_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 14),
        chw_ids=frozenset({3001, 3002}),
    )

    call = ch_mock.query_rows.await_args_list[0]
    assert set(call.kwargs["parameters"]["chw_ids"]) == {3001, 3002}
    assert "chw_id IN {chw_ids:Array(Int64)}" in call.args[0]


@pytest.mark.asyncio
async def test_get_digital_help_module_usage_empty_chw_ids_short_circuits() -> None:
    ch_mock = MagicMock()
    ch_mock.query_rows = AsyncMock(return_value=[{"should": "not_run"}])

    result = await DashboardAnalyticsService(ch_mock, None).get_digital_help_module_usage(
        tenant_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 14),
        chw_ids=frozenset(),
    )

    assert result.total_modules == 0
    assert result.modules == []
    ch_mock.query_rows.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_digital_help_module_questions_passes_chw_ids() -> None:
    module_id = uuid4()
    ch_mock = MagicMock()
    ch_mock.query_rows = AsyncMock(side_effect=[[{"total_questions": 0}], []])

    await DashboardAnalyticsService(ch_mock, None).get_digital_help_module_questions(
        module_id=module_id,
        tenant_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 14),
        chw_ids=frozenset({3001}),
    )

    for call in ch_mock.query_rows.await_args_list:
        assert call.kwargs["parameters"]["chw_ids"] == [3001]
        assert "chw_id IN {chw_ids:Array(Int64)}" in call.args[0]


@pytest.mark.asyncio
async def test_get_digital_help_module_requests_empty_chw_ids_short_circuits() -> None:
    module_id = uuid4()
    ch_mock = MagicMock()
    ch_mock.query_rows = AsyncMock(return_value=[{"total_requests": 99}])

    result = await DashboardAnalyticsService(ch_mock, None).get_digital_help_module_requests(
        module_id=module_id,
        tenant_id=None,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 14),
        chw_ids=frozenset(),
    )

    assert result.total_requests == 0
    assert result.requests == []
    ch_mock.query_rows.assert_not_awaited()
