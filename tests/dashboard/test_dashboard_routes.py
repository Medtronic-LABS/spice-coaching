"""Dashboard route tests that do not require PostgreSQL."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from mc_contracts.dashboard import (
    DashboardUserSummary,
    DigitalHelpModuleQuestionItem,
    DigitalHelpModuleQuestionsResponse,
    DigitalHelpModuleRequestItem,
    DigitalHelpModuleRequestsResponse,
    DigitalHelpModuleUsageItem,
    DigitalHelpModuleUsageResponse,
)
from mc_foundation.problem import register_problem_handlers
from platform_service.api.dashboard import router as dashboard_router
from platform_service.config import get_settings
from platform_service.deps import get_clickhouse_client, get_db

from tests.conftest import platform_path

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def app() -> AsyncIterator[FastAPI]:
    app_obj = FastAPI()
    register_problem_handlers(
        app_obj,
        validation_error_type=RequestValidationError,
        http_exception_type=HTTPException,
    )
    # Auth-off: hierarchy viewer is unrestricted without a spice_user on the request.
    auth_off = get_settings().model_copy(update={"spice_auth_enabled": False})
    with patch("platform_service.api.dashboard.get_settings", return_value=auth_off):
        api_router = APIRouter(prefix=auth_off.api_root_path_normalized)
        api_router.include_router(dashboard_router)
        app_obj.include_router(api_router)

        ch_mock = MagicMock()
        ch_mock.query_rows = AsyncMock(return_value=[])
        app_obj.dependency_overrides[get_clickhouse_client] = lambda: ch_mock

        async def _override_get_db() -> AsyncIterator[MagicMock]:
            yield MagicMock()

        app_obj.dependency_overrides[get_db] = _override_get_db
        yield app_obj
        app_obj.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestDigitalHelpModuleUsageRoute:
    @patch(
        "platform_service.api.dashboard.DashboardAnalyticsService.get_digital_help_module_usage",
        new_callable=AsyncMock,
    )
    async def test_digital_help_modules_returns_ranked_modules(
        self,
        mock_get: AsyncMock,
        client: AsyncClient,
    ) -> None:
        family_a = uuid4()
        family_b = uuid4()
        module_a_id = uuid4()
        module_b_id = uuid4()
        mock_get.return_value = DigitalHelpModuleUsageResponse(
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            total_digital_help=10,
            total_module_requested=3,
            total_modules=2,
            limit=10,
            offset=0,
            modules=[
                DigitalHelpModuleUsageItem(
                    module_id=module_a_id,
                    module_family_id=family_a,
                    digital_help_count=7,
                    module_requested_count=3,
                    title={"bn": "Module A", "en": "Module A EN"},
                ),
                DigitalHelpModuleUsageItem(
                    module_id=module_b_id,
                    module_family_id=family_b,
                    digital_help_count=3,
                    module_requested_count=0,
                    title={"bn": "Module B"},
                ),
            ],
        )

        resp = await client.get(
            platform_path(
                "/dashboard/digital-help-modules?from_date=2026-01-01&to_date=2026-01-31&limit=10&offset=0"
            )
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["from_date"] == "2026-01-01"
        assert data["to_date"] == "2026-01-31"
        assert data["total_digital_help"] == 10
        assert data["total_module_requested"] == 3
        assert data["total_modules"] == 2
        assert data["limit"] == 10
        assert data["offset"] == 0
        assert len(data["modules"]) == 2
        assert data["modules"][0]["digital_help_count"] == 7
        assert data["modules"][0]["module_requested_count"] == 3
        assert data["modules"][0]["module_id"] == str(module_a_id)
        assert data["modules"][0]["title"]["bn"] == "Module A"
        mock_get.assert_awaited_once()
        assert mock_get.await_args.kwargs["from_date"] == date(2026, 1, 1)
        assert mock_get.await_args.kwargs["to_date"] == date(2026, 1, 31)
        assert mock_get.await_args.kwargs["limit"] == 10
        assert mock_get.await_args.kwargs["offset"] == 0
        assert mock_get.await_args.kwargs["chw_ids"] is None

    @patch(
        "platform_service.api.dashboard._resolve_dashboard_chw_ids",
        new_callable=AsyncMock,
    )
    @patch(
        "platform_service.api.dashboard.DashboardAnalyticsService.get_digital_help_module_usage",
        new_callable=AsyncMock,
    )
    async def test_digital_help_modules_passes_hierarchy_chw_ids(
        self,
        mock_get: AsyncMock,
        mock_resolve: AsyncMock,
        client: AsyncClient,
    ) -> None:
        mock_resolve.return_value = frozenset({3001, 3002})
        mock_get.return_value = DigitalHelpModuleUsageResponse(
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            total_digital_help=0,
            total_module_requested=0,
            total_modules=0,
            limit=20,
            offset=0,
            modules=[],
        )
        resp = await client.get(
            platform_path("/dashboard/digital-help-modules?from_date=2026-01-01&to_date=2026-01-31")
        )
        assert resp.status_code == 200
        mock_resolve.assert_awaited_once()
        assert mock_resolve.await_args.kwargs["include_self"] is False
        assert mock_get.await_args.kwargs["chw_ids"] == frozenset({3001, 3002})

    @patch(
        "platform_service.api.dashboard._resolve_dashboard_chw_ids",
        new_callable=AsyncMock,
    )
    @patch(
        "platform_service.api.dashboard.DashboardAnalyticsService.get_digital_help_module_usage",
        new_callable=AsyncMock,
    )
    async def test_digital_help_modules_passes_geography_filters(
        self,
        mock_get: AsyncMock,
        mock_resolve: AsyncMock,
        client: AsyncClient,
    ) -> None:
        mock_resolve.return_value = frozenset({3001})
        mock_get.return_value = DigitalHelpModuleUsageResponse(
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            total_digital_help=0,
            total_module_requested=0,
            total_modules=0,
            limit=20,
            offset=0,
            modules=[],
        )
        resp = await client.get(
            platform_path(
                "/dashboard/digital-help-modules"
                "?from_date=2026-01-01&to_date=2026-01-31"
                "&division_id=1&district_id=2&upazila_id=3"
            )
        )
        assert resp.status_code == 200
        mock_resolve.assert_awaited_once()
        assert mock_resolve.await_args.kwargs["division_ids"] == [1]
        assert mock_resolve.await_args.kwargs["district_ids"] == [2]
        assert mock_resolve.await_args.kwargs["upazila_ids"] == [3]
        assert mock_get.await_args.kwargs["chw_ids"] == frozenset({3001})

    @patch(
        "platform_service.api.dashboard.DashboardAnalyticsService.get_digital_help_module_usage",
        new_callable=AsyncMock,
    )
    async def test_digital_help_modules_invalid_geography_id_returns_422(
        self,
        mock_get: AsyncMock,
        client: AsyncClient,
    ) -> None:
        resp = await client.get(
            platform_path(
                "/dashboard/digital-help-modules"
                "?from_date=2026-01-01&to_date=2026-01-31&division_id=not-an-id"
            )
        )
        assert resp.status_code == 422
        mock_get.assert_not_awaited()

    @patch(
        "platform_service.api.dashboard.DashboardAnalyticsService.get_digital_help_module_usage",
        new_callable=AsyncMock,
    )
    async def test_digital_help_modules_invalid_date_range_returns_422(
        self,
        mock_get: AsyncMock,
        client: AsyncClient,
    ) -> None:
        resp = await client.get(
            platform_path("/dashboard/digital-help-modules?from_date=2026-02-01&to_date=2026-01-01")
        )
        assert resp.status_code == 422
        mock_get.assert_not_awaited()

    async def test_digital_help_modules_missing_dates_returns_422(
        self,
        client: AsyncClient,
    ) -> None:
        resp = await client.get(platform_path("/dashboard/digital-help-modules?limit=10"))
        assert resp.status_code == 422

    @patch(
        "platform_service.api.dashboard.DashboardAnalyticsService.get_digital_help_module_usage",
        new_callable=AsyncMock,
    )
    async def test_digital_help_modules_invalid_view_returns_422(
        self,
        mock_get: AsyncMock,
        client: AsyncClient,
    ) -> None:
        resp = await client.get(
            platform_path("/dashboard/digital-help-modules?from_date=2026-01-01&to_date=2026-01-31&view=am")
        )
        assert resp.status_code == 422
        mock_get.assert_not_awaited()

    @patch(
        "platform_service.api.dashboard.DashboardAnalyticsService.get_digital_help_module_usage",
        new_callable=AsyncMock,
    )
    async def test_digital_help_modules_auth_off_ignores_view(
        self,
        mock_get: AsyncMock,
        client: AsyncClient,
    ) -> None:
        mock_get.return_value = DigitalHelpModuleUsageResponse(
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            total_digital_help=0,
            total_module_requested=0,
            total_modules=0,
            limit=20,
            offset=0,
            modules=[],
        )
        resp = await client.get(
            platform_path("/dashboard/digital-help-modules?from_date=2026-01-01&to_date=2026-01-31&view=po")
        )
        assert resp.status_code == 200
        assert mock_get.await_args.kwargs["chw_ids"] is None

    @patch(
        "platform_service.api.dashboard._apply_optional_actor_view",
        new_callable=AsyncMock,
    )
    @patch(
        "platform_service.api.dashboard._resolve_dashboard_chw_ids",
        new_callable=AsyncMock,
    )
    @patch(
        "platform_service.api.dashboard.DashboardAnalyticsService.get_digital_help_module_usage",
        new_callable=AsyncMock,
    )
    async def test_digital_help_modules_passes_narrowed_chw_ids_from_view(
        self,
        mock_get: AsyncMock,
        mock_resolve: AsyncMock,
        mock_apply_view: AsyncMock,
        client: AsyncClient,
    ) -> None:
        from mc_contracts.enums import DashboardActorView

        mock_resolve.return_value = frozenset({3001, 3002})
        mock_apply_view.return_value = frozenset({3001})
        mock_get.return_value = DigitalHelpModuleUsageResponse(
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            total_digital_help=0,
            total_module_requested=0,
            total_modules=0,
            limit=20,
            offset=0,
            modules=[],
        )
        resp = await client.get(
            platform_path("/dashboard/digital-help-modules?from_date=2026-01-01&to_date=2026-01-31&view=sk")
        )
        assert resp.status_code == 200
        assert mock_apply_view.await_args.args[2] == frozenset({3001, 3002})
        assert mock_apply_view.await_args.args[3] == DashboardActorView.SK
        assert mock_get.await_args.kwargs["chw_ids"] == frozenset({3001})


class TestDigitalHelpModuleQuestionsRoute:
    @patch(
        "platform_service.api.dashboard.DashboardAnalyticsService.get_digital_help_module_questions",
        new_callable=AsyncMock,
    )
    async def test_digital_help_module_questions_returns_payload(
        self,
        mock_get: AsyncMock,
        client: AsyncClient,
    ) -> None:
        module_id = uuid4()
        mock_get.return_value = DigitalHelpModuleQuestionsResponse(
            module_id=module_id,
            title={"bn": "Module A", "en": "Module A EN"},
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            questions=[
                DigitalHelpModuleQuestionItem(
                    question="How to treat fever?",
                    occurrence_count=3,
                    last_asked_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
                    asked_by=DashboardUserSummary(
                        user_id=3001,
                        user_name="SK One",
                        user_role="SHASTIYA_KORMI",
                    ),
                )
            ],
            total_questions=1,
            total_pages=1,
            limit=50,
            offset=0,
        )

        resp = await client.get(
            platform_path(
                f"/dashboard/digital-help-modules/{module_id}/questions"
                "?from_date=2026-01-01&to_date=2026-01-31&limit=50&offset=0"
            )
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["module_id"] == str(module_id)
        assert data["title"]["bn"] == "Module A"
        assert data["total_questions"] == 1
        assert data["questions"][0]["question"] == "How to treat fever?"
        assert data["questions"][0]["occurrence_count"] == 3
        assert data["questions"][0]["asked_by"]["user_id"] == 3001
        assert data["questions"][0]["asked_by"]["user_name"] == "SK One"
        mock_get.assert_awaited_once()
        assert mock_get.await_args.kwargs["module_id"] == module_id
        assert mock_get.await_args.kwargs["from_date"] == date(2026, 1, 1)
        assert mock_get.await_args.kwargs["to_date"] == date(2026, 1, 31)
        assert mock_get.await_args.kwargs["limit"] == 50
        assert mock_get.await_args.kwargs["offset"] == 0

    @patch(
        "platform_service.api.dashboard.DashboardAnalyticsService.get_digital_help_module_questions",
        new_callable=AsyncMock,
    )
    async def test_digital_help_module_questions_invalid_date_range_returns_422(
        self,
        mock_get: AsyncMock,
        client: AsyncClient,
    ) -> None:
        module_id = uuid4()
        resp = await client.get(
            platform_path(
                f"/dashboard/digital-help-modules/{module_id}/questions"
                "?from_date=2026-02-01&to_date=2026-01-01"
            )
        )
        assert resp.status_code == 422
        mock_get.assert_not_awaited()


class TestDigitalHelpModuleRequestsRoute:
    @patch(
        "platform_service.api.dashboard.DashboardAnalyticsService.get_digital_help_module_requests",
        new_callable=AsyncMock,
    )
    async def test_digital_help_module_requests_returns_paginated_payload(
        self,
        mock_get: AsyncMock,
        client: AsyncClient,
    ) -> None:
        module_id = uuid4()
        mock_get.return_value = DigitalHelpModuleRequestsResponse(
            module_id=module_id,
            title={"bn": "Module A"},
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            requests=[
                DigitalHelpModuleRequestItem(
                    requested_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
                    reason="Need training",
                    requested_by=DashboardUserSummary(
                        user_id=3001,
                        user_name="SK One",
                        user_role="SHASTIYA_KORMI",
                    ),
                )
            ],
            total_requests=7,
            total_pages=1,
            limit=50,
            offset=0,
        )

        resp = await client.get(
            platform_path(
                f"/dashboard/digital-help-modules/{module_id}/requests"
                "?from_date=2026-01-01&to_date=2026-01-31&limit=50&offset=0"
            )
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["module_id"] == str(module_id)
        assert data["total_requests"] == 7
        assert data["requests"][0]["reason"] == "Need training"
        assert data["requests"][0]["requested_by"]["user_id"] == 3001
        assert data["title"]["bn"] == "Module A"
        mock_get.assert_awaited_once()
        assert mock_get.await_args.kwargs["module_id"] == module_id
        assert mock_get.await_args.kwargs["limit"] == 50
        assert mock_get.await_args.kwargs["offset"] == 0

    @patch(
        "platform_service.api.dashboard.DashboardAnalyticsService.get_digital_help_module_requests",
        new_callable=AsyncMock,
    )
    async def test_digital_help_module_requests_invalid_date_range_returns_422(
        self,
        mock_get: AsyncMock,
        client: AsyncClient,
    ) -> None:
        module_id = uuid4()
        resp = await client.get(
            platform_path(
                f"/dashboard/digital-help-modules/{module_id}/requests"
                "?from_date=2026-02-01&to_date=2026-01-01"
            )
        )
        assert resp.status_code == 422
        mock_get.assert_not_awaited()


class TestModuleCreationSuggestionsRoutes:
    @patch("platform_service.api.dashboard.ModuleCreationSuggestionService")
    async def test_list_suggestions(
        self,
        mock_service_cls: MagicMock,
        client: AsyncClient,
    ) -> None:
        from mc_contracts.dashboard import (
            ModuleCreationSuggestionListItem,
            ModuleCreationSuggestionListResponse,
        )

        suggestion_id = uuid4()
        mock_service = MagicMock()
        mock_service.list_suggestions = AsyncMock(
            return_value=ModuleCreationSuggestionListResponse(
                from_date=date(2026, 7, 1),
                to_date=date(2026, 7, 31),
                suggestions=[
                    ModuleCreationSuggestionListItem(
                        id=suggestion_id,
                        suggestion_date=date(2026, 7, 29),
                        suggestion_kind="proposed_topic",
                        proposed_topic="Neonatal resuscitation",
                        display_title="Neonatal resuscitation",
                        rationale="Frequent free-text requests",
                        question_count=0,
                        request_count=5,
                        evidence_count=5,
                        rank=1,
                        computed_at=datetime(2026, 7, 30, 4, 0, tzinfo=UTC),
                    )
                ],
                total_suggestions=1,
                total_pages=1,
                limit=20,
                offset=0,
            )
        )
        mock_service_cls.return_value = mock_service
        resp = await client.get(
            platform_path("/dashboard/module-creation-suggestions?from_date=2026-07-01&to_date=2026-07-31")
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_suggestions"] == 1
        assert data["suggestions"][0]["id"] == str(suggestion_id)
        assert data["suggestions"][0]["suggestion_kind"] == "proposed_topic"
        mock_service.list_suggestions.assert_awaited_once()
        assert mock_service.list_suggestions.await_args.kwargs["visible_chw_ids"] is None

    @patch("platform_service.api.dashboard._resolve_dashboard_chw_ids", new_callable=AsyncMock)
    @patch("platform_service.api.dashboard.ModuleCreationSuggestionService")
    async def test_list_suggestions_passes_visible_chw_ids(
        self,
        mock_service_cls: MagicMock,
        mock_resolve: AsyncMock,
        client: AsyncClient,
    ) -> None:
        from mc_contracts.dashboard import ModuleCreationSuggestionListResponse

        mock_resolve.return_value = frozenset({3001})
        mock_service = MagicMock()
        mock_service.list_suggestions = AsyncMock(
            return_value=ModuleCreationSuggestionListResponse(
                from_date=date(2026, 7, 1),
                to_date=date(2026, 7, 31),
                suggestions=[],
                total_suggestions=0,
                total_pages=0,
                limit=20,
                offset=0,
            )
        )
        mock_service_cls.return_value = mock_service
        resp = await client.get(
            platform_path("/dashboard/module-creation-suggestions?from_date=2026-07-01&to_date=2026-07-31")
        )
        assert resp.status_code == 200
        assert mock_service.list_suggestions.await_args.kwargs["visible_chw_ids"] == frozenset({3001})

    @patch("platform_service.api.dashboard._apply_optional_actor_view", new_callable=AsyncMock)
    @patch("platform_service.api.dashboard._resolve_dashboard_chw_ids", new_callable=AsyncMock)
    @patch("platform_service.api.dashboard.ModuleCreationSuggestionService")
    async def test_list_suggestions_applies_actor_view(
        self,
        mock_service_cls: MagicMock,
        mock_resolve: AsyncMock,
        mock_apply_view: AsyncMock,
        client: AsyncClient,
    ) -> None:
        from mc_contracts.dashboard import ModuleCreationSuggestionListResponse
        from mc_contracts.enums import DashboardActorView

        mock_resolve.return_value = frozenset({3001, 3002})
        mock_apply_view.return_value = frozenset({3002})
        mock_service = MagicMock()
        mock_service.list_suggestions = AsyncMock(
            return_value=ModuleCreationSuggestionListResponse(
                from_date=date(2026, 7, 1),
                to_date=date(2026, 7, 31),
                suggestions=[],
                total_suggestions=0,
                total_pages=0,
                limit=20,
                offset=0,
            )
        )
        mock_service_cls.return_value = mock_service
        resp = await client.get(
            platform_path(
                "/dashboard/module-creation-suggestions?from_date=2026-07-01&to_date=2026-07-31&view=po"
            )
        )
        assert resp.status_code == 200
        assert mock_apply_view.await_args.args[3] == DashboardActorView.PO
        assert mock_service.list_suggestions.await_args.kwargs["visible_chw_ids"] == frozenset({3002})

    @patch("platform_service.api.dashboard.ModuleCreationSuggestionService")
    async def test_list_invalid_date_range_returns_422(
        self,
        mock_service_cls: MagicMock,
        client: AsyncClient,
    ) -> None:
        resp = await client.get(
            platform_path("/dashboard/module-creation-suggestions?from_date=2026-07-31&to_date=2026-07-01")
        )
        assert resp.status_code == 422
        mock_service_cls.assert_not_called()

    @patch("platform_service.api.dashboard.ModuleCreationSuggestionService")
    async def test_detail_returns_evidence(
        self,
        mock_service_cls: MagicMock,
        client: AsyncClient,
    ) -> None:
        from mc_contracts.dashboard import (
            DashboardUserSummary,
            ModuleCreationSuggestionDetailResponse,
            ModuleCreationSuggestionEvidenceItem,
            ModuleCreationSuggestionListItem,
        )

        suggestion_id = uuid4()
        mock_service = MagicMock()
        mock_service.get_detail = AsyncMock(
            return_value=ModuleCreationSuggestionDetailResponse(
                suggestion=ModuleCreationSuggestionListItem(
                    id=suggestion_id,
                    suggestion_date=date(2026, 7, 29),
                    suggestion_kind="matched_draft",
                    matched_module_id=uuid4(),
                    display_title="Draft BP",
                    rationale="Matches draft",
                    question_count=2,
                    request_count=1,
                    evidence_count=3,
                    rank=1,
                    computed_at=datetime(2026, 7, 30, 4, 0, tzinfo=UTC),
                ),
                questions=[
                    ModuleCreationSuggestionEvidenceItem(
                        source="digital_help",
                        text="BP threshold?",
                        occurrence_count=2,
                        prompted_by=DashboardUserSummary(user_id=3001, user_name="SK One"),
                    )
                ],
                requests=[
                    ModuleCreationSuggestionEvidenceItem(
                        source="module_requested",
                        text="Hypertension module",
                        occurrence_count=1,
                        prompted_by=DashboardUserSummary(user_id=3001, user_name="SK One"),
                    )
                ],
            )
        )
        mock_service_cls.return_value = mock_service
        resp = await client.get(platform_path(f"/dashboard/module-creation-suggestions/{suggestion_id}"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["suggestion"]["id"] == str(suggestion_id)
        assert len(data["questions"]) == 1
        assert len(data["requests"]) == 1
        mock_service.get_detail.assert_awaited_once()

    @patch("platform_service.api.dashboard._apply_optional_actor_view", new_callable=AsyncMock)
    @patch("platform_service.api.dashboard._resolve_dashboard_chw_ids", new_callable=AsyncMock)
    @patch("platform_service.api.dashboard.ModuleCreationSuggestionService")
    async def test_detail_applies_actor_view(
        self,
        mock_service_cls: MagicMock,
        mock_resolve: AsyncMock,
        mock_apply_view: AsyncMock,
        client: AsyncClient,
    ) -> None:
        from mc_contracts.dashboard import (
            ModuleCreationSuggestionDetailResponse,
            ModuleCreationSuggestionListItem,
        )
        from mc_contracts.enums import DashboardActorView

        suggestion_id = uuid4()
        mock_resolve.return_value = frozenset({3001, 3002})
        mock_apply_view.return_value = frozenset({3001})
        mock_service = MagicMock()
        mock_service.get_detail = AsyncMock(
            return_value=ModuleCreationSuggestionDetailResponse(
                suggestion=ModuleCreationSuggestionListItem(
                    id=suggestion_id,
                    suggestion_date=date(2026, 7, 29),
                    suggestion_kind="proposed_topic",
                    proposed_topic="Topic",
                    display_title="Topic",
                    rationale="why",
                    question_count=1,
                    request_count=0,
                    evidence_count=1,
                    rank=1,
                    computed_at=datetime(2026, 7, 30, 4, 0, tzinfo=UTC),
                ),
                questions=[],
                requests=[],
            )
        )
        mock_service_cls.return_value = mock_service
        resp = await client.get(
            platform_path(f"/dashboard/module-creation-suggestions/{suggestion_id}?view=sk")
        )
        assert resp.status_code == 200
        assert mock_apply_view.await_args.args[3] == DashboardActorView.SK
        assert mock_service.get_detail.await_args.kwargs["visible_chw_ids"] == frozenset({3001})

    @patch("platform_service.api.dashboard.ModuleCreationSuggestionService")
    async def test_detail_not_found_returns_404(
        self,
        mock_service_cls: MagicMock,
        client: AsyncClient,
    ) -> None:
        suggestion_id = uuid4()
        mock_service = MagicMock()
        mock_service.get_detail = AsyncMock(side_effect=LookupError(f"suggestion not found: {suggestion_id}"))
        mock_service_cls.return_value = mock_service
        resp = await client.get(platform_path(f"/dashboard/module-creation-suggestions/{suggestion_id}"))
        assert resp.status_code == 404


class TestModuleDemandSummaryRoute:
    @patch(
        "platform_service.api.dashboard.ModuleDemandSummaryService.get_summary",
        new_callable=AsyncMock,
    )
    async def test_module_demand_summary_returns_structured_body(
        self,
        mock_get: AsyncMock,
        client: AsyncClient,
    ) -> None:
        from mc_contracts.dashboard import ModuleDemandPatternItem, ModuleDemandSummaryResponse

        mock_get.return_value = ModuleDemandSummaryResponse(
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
            title="Insights from Module Usage",
            date_label="Jul 1–31, 2026",
            narrative="Most demand can be addressed with existing published modules.",
            demand_pattern=[
                ModuleDemandPatternItem(
                    bucket="assign",
                    title="Existing coverage",
                    description="Demand is concentrated around a few published modules",
                )
            ],
        )
        resp = await client.get(
            platform_path("/dashboard/module-demand-summary?from_date=2026-07-01&to_date=2026-07-31")
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" not in data
        assert data["title"] == "Insights from Module Usage"
        assert data["date_label"] == "Jul 1–31, 2026"
        assert data["narrative"].startswith("Most demand")
        assert data["empty_message"] is None
        assert data["demand_pattern"][0]["bucket"] == "assign"
        assert data["from_date"] == "2026-07-01"
        assert data["to_date"] == "2026-07-31"
        mock_get.assert_awaited_once()
        assert mock_get.await_args.kwargs["top_limit"] == 10

    @patch(
        "platform_service.api.dashboard.ModuleDemandSummaryService.get_summary",
        new_callable=AsyncMock,
    )
    async def test_module_demand_summary_forwards_top_limit(
        self,
        mock_get: AsyncMock,
        client: AsyncClient,
    ) -> None:
        from mc_contracts.dashboard import ModuleDemandSummaryResponse

        mock_get.return_value = ModuleDemandSummaryResponse(
            from_date=date(2026, 7, 1),
            to_date=date(2026, 7, 31),
            title="Insights from Module Usage",
            date_label="Jul 1–31, 2026",
            empty_message="No module demand for your team in Jul 1–31, 2026.",
        )
        resp = await client.get(
            platform_path(
                "/dashboard/module-demand-summary?from_date=2026-07-01&to_date=2026-07-31&top_limit=5"
            )
        )
        assert resp.status_code == 200
        assert mock_get.await_args.kwargs["top_limit"] == 5

    @patch(
        "platform_service.api.dashboard.ModuleDemandSummaryService.get_summary",
        new_callable=AsyncMock,
    )
    async def test_module_demand_summary_invalid_date_range_returns_422(
        self,
        mock_get: AsyncMock,
        client: AsyncClient,
    ) -> None:
        resp = await client.get(
            platform_path("/dashboard/module-demand-summary?from_date=2026-07-31&to_date=2026-07-01")
        )
        assert resp.status_code == 422
        mock_get.assert_not_awaited()
