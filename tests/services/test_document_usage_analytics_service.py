"""Document usage analytics service tests (mocked ClickHouse)."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from mc_foundation.problem import AppError
from platform_service.services.dashboard_hierarchy import OrgUser
from platform_service.services.document_usage_analytics_service import (
    DocumentUsageAnalyticsService,
    DocumentUsageFilter,
)

pytestmark = pytest.mark.asyncio


def _filters(**overrides: object) -> DocumentUsageFilter:
    base: dict[str, object] = {
        "from_date": date(2026, 4, 1),
        "to_date": date(2026, 4, 30),
        "unrestricted_viewer": True,
    }
    base.update(overrides)
    return DocumentUsageFilter(**base)  # type: ignore[arg-type]


def _org_user(
    user_id: int,
    *,
    role: str,
    parent_id: int | None = None,
) -> OrgUser:
    return OrgUser(
        id=user_id,
        name=f"user-{user_id}",
        role=role,
        district_id=1,
        district=None,
        division_id=None,
        division=None,
        upazila_ids=frozenset(),
        upazila_names=frozenset(),
        parent_id=parent_id,
    )


class TestDocumentUsageAnalyticsService:
    async def test_usage_empty_when_chw_filter_empty(self) -> None:
        ch = MagicMock()
        ch.query_rows = AsyncMock()
        service = DocumentUsageAnalyticsService(ch)
        result = await service.get_usage(_filters(viewer_id=401, unrestricted_viewer=False))
        assert result.total_views == 0
        assert result.unique_documents == 0
        assert result.documents == []
        assert result.events == []
        ch.query_rows.assert_not_called()

    async def test_usage_rejects_out_of_subtree_user_id(self) -> None:
        ch = MagicMock()
        ch.query_rows = AsyncMock()
        session = MagicMock()
        service = DocumentUsageAnalyticsService(ch, session)
        users = {
            10: _org_user(10, role="PO"),
            11: _org_user(11, role="SHASTIYA_KORMI", parent_id=10),
            99: _org_user(99, role="PO"),
        }
        with patch(
            "platform_service.services.document_usage_analytics_service.org_user_index",
            new=AsyncMock(return_value=users),
        ):
            with pytest.raises(AppError) as exc_info:
                await service.get_usage(
                    _filters(
                        viewer_id=10,
                        unrestricted_viewer=False,
                        user_id=99,
                    )
                )
        assert exc_info.value.status == 403
        ch.query_rows.assert_not_called()

    async def test_usage_combines_summary_documents_and_events(self) -> None:
        doc_a = uuid4()
        doc_b = uuid4()
        viewed = datetime(2026, 4, 28, 12, 0, 0)
        ch = MagicMock()
        ch.query_rows = AsyncMock(
            side_effect=[
                # summary
                [{"total_views": 5, "unique_documents": 2, "unique_users": 3}],
                # top
                [
                    {"source_document_id": str(doc_a), "view_count": 3},
                    {"source_document_id": str(doc_b), "view_count": 2},
                ],
                # document row count
                [{"total_document_rows": 2}],
                # document page
                [
                    {
                        "source_document_id": str(doc_a),
                        "total_views": 3,
                        "unique_users": 2,
                    }
                ],
                # last viewed
                [
                    {
                        "source_document_id": str(doc_a),
                        "last_chw_id": 395,
                        "last_viewed_at": viewed,
                    }
                ],
                # event count
                [{"total_events": 1}],
                # events page
                [
                    {
                        "event_id": "evt-1",
                        "source_document_id": str(doc_a),
                        "chw_id": 401,
                        "upazila_id": "Lalmonirhat Sadar",
                        "viewed_at": viewed,
                    }
                ],
            ]
        )
        service = DocumentUsageAnalyticsService(ch)
        result = await service.get_usage(_filters())
        assert result.total_views == 5
        assert result.unique_documents == 2
        assert result.unique_users == 3
        assert [item.document_id for item in result.top_documents] == [doc_a, doc_b]
        assert result.top_documents[0].view_count == 3
        assert result.total_document_rows == 2
        assert result.documents[0].last_viewed_by_user_id == 395
        assert result.documents[0].last_viewed_by_user_name is None
        assert result.total_events == 1
        assert result.events[0].user_role is None
        assert result.events[0].viewed_at == viewed
        assert result.documents[0].last_viewed_at == viewed
        last_viewed_sql = ch.query_rows.await_args_list[4].args[0]
        assert "max(timestamp_local) AS last_viewed_at" in last_viewed_sql
        assert "argMax(chw_id, timestamp_local)" in last_viewed_sql
        events_sql = ch.query_rows.await_args_list[6].args[0]
        assert "timestamp_local AS viewed_at" in events_sql
        assert "ORDER BY timestamp_utc DESC" in events_sql

    async def test_usage_response_uses_local_not_utc_wall_clock(self) -> None:
        """Response timestamps come from timestamp_local even when UTC differs."""
        doc_a = uuid4()
        viewed_local = datetime(2026, 4, 28, 18, 0, 0)
        ch = MagicMock()
        ch.query_rows = AsyncMock(
            side_effect=[
                [{"total_views": 1, "unique_documents": 1, "unique_users": 1}],
                [{"source_document_id": str(doc_a), "view_count": 1}],
                [{"total_document_rows": 1}],
                [
                    {
                        "source_document_id": str(doc_a),
                        "total_views": 1,
                        "unique_users": 1,
                    }
                ],
                [
                    {
                        "source_document_id": str(doc_a),
                        "last_chw_id": 395,
                        "last_viewed_at": viewed_local,
                    }
                ],
                [{"total_events": 1}],
                [
                    {
                        "event_id": "evt-local",
                        "source_document_id": str(doc_a),
                        "chw_id": 395,
                        "upazila_id": None,
                        "viewed_at": viewed_local,
                    }
                ],
            ]
        )
        result = await DocumentUsageAnalyticsService(ch).get_usage(_filters())
        assert result.documents[0].last_viewed_at == viewed_local
        assert result.events[0].viewed_at == viewed_local
        assert viewed_local != datetime(2026, 4, 28, 12, 0, 0)

    async def test_usage_title_query_narrows_documents_only(self) -> None:
        doc_a = uuid4()
        doc_b = uuid4()
        viewed = datetime(2026, 4, 28, 12, 0, 0)
        ch = MagicMock()
        ch.query_rows = AsyncMock(
            side_effect=[
                # summary (unfiltered)
                [{"total_views": 5, "unique_documents": 2, "unique_users": 3}],
                # top (unfiltered)
                [
                    {"source_document_id": str(doc_a), "view_count": 3},
                    {"source_document_id": str(doc_b), "view_count": 2},
                ],
                # document row count (title-filtered)
                [{"total_document_rows": 1}],
                # document page (title-filtered)
                [
                    {
                        "source_document_id": str(doc_a),
                        "total_views": 3,
                        "unique_users": 2,
                    }
                ],
                # last viewed
                [
                    {
                        "source_document_id": str(doc_a),
                        "last_chw_id": 395,
                        "last_viewed_at": viewed,
                    }
                ],
                # event count (unfiltered)
                [{"total_events": 1}],
                # events page (unfiltered)
                [
                    {
                        "event_id": "evt-1",
                        "source_document_id": str(doc_b),
                        "chw_id": 401,
                        "upazila_id": None,
                        "viewed_at": viewed,
                    }
                ],
            ]
        )
        service = DocumentUsageAnalyticsService(ch)
        with patch.object(
            service,
            "_resolve_title_document_ids",
            new=AsyncMock(return_value=frozenset([doc_a])),
        ):
            result = await service.get_usage(_filters(title_query="protocol"))

        assert result.total_views == 5
        assert result.unique_documents == 2
        assert [item.document_id for item in result.top_documents] == [doc_a, doc_b]
        assert result.total_document_rows == 1
        assert [row.document_id for row in result.documents] == [doc_a]
        assert result.total_events == 1
        count_sql = ch.query_rows.await_args_list[2].args[0]
        count_params = ch.query_rows.await_args_list[2].kwargs["parameters"]
        assert "title_doc_ids" in count_sql
        assert count_params["title_doc_ids"] == [str(doc_a)]
        summary_params = ch.query_rows.await_args_list[0].kwargs["parameters"]
        assert "title_doc_ids" not in summary_params

    async def test_usage_title_query_no_matches_empties_documents(self) -> None:
        doc_a = uuid4()
        ch = MagicMock()
        ch.query_rows = AsyncMock(
            side_effect=[
                [{"total_views": 3, "unique_documents": 1, "unique_users": 1}],
                [{"source_document_id": str(doc_a), "view_count": 3}],
                [{"total_events": 0}],
                [],
            ]
        )
        service = DocumentUsageAnalyticsService(ch)
        with patch.object(
            service,
            "_resolve_title_document_ids",
            new=AsyncMock(return_value=frozenset()),
        ):
            result = await service.get_usage(_filters(title_query="zzz-missing"))

        assert result.total_views == 3
        assert result.total_document_rows == 0
        assert result.documents == []
        assert len(ch.query_rows.await_args_list) == 4
