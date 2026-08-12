"""Tests for GET /dashboard/team-activity and member questions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from mc_contracts.dashboard import (
    TeamActivityResponse,
    TeamActivitySummary,
    TeamMemberQuestionItem,
    TeamMemberQuestionsResponse,
)
from mc_contracts.enums import HierarchyRole
from mc_contracts.errors import ErrorCode
from mc_foundation.problem import AppError, register_problem_handlers
from platform_service.api.dashboard import router as dashboard_router
from platform_service.auth.spice_context import SpiceUserContext
from platform_service.auth.spice_identity import TeamActivityScope
from platform_service.config import get_settings
from platform_service.deps import get_clickhouse_client, get_db
from platform_service.services.dashboard_hierarchy import OrgUser

from tests.conftest import platform_path

pytestmark = pytest.mark.asyncio

ORGANIZER_ID = 401
AM_ID = 100
SK_ID = 395
TEST_TENANT_ID = 7


def _org_user(
    user_id: int,
    *,
    role: str,
    parent_id: int | None = None,
    name: str | None = None,
) -> OrgUser:
    return OrgUser(
        id=user_id,
        name=name or f"user-{user_id}",
        role=role,
        district_id=1,
        district=None,
        upazila_ids=frozenset(),
        upazila_names=frozenset(),
        parent_id=parent_id,
    )


@pytest_asyncio.fixture
async def app(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FastAPI]:
    # Team-activity list/questions tests exercise auth-on device-plane rules.
    auth_on = get_settings().model_copy(update={"spice_auth_enabled": True})
    monkeypatch.setattr("platform_service.auth.spice_identity.get_settings", lambda: auth_on)
    monkeypatch.setattr("platform_service.auth.spice_user.get_settings", lambda: auth_on)
    monkeypatch.setattr(
        "platform_service.auth.spice_identity.org_user_index",
        AsyncMock(return_value={}),
    )

    app_obj = FastAPI()
    register_problem_handlers(
        app_obj,
        validation_error_type=RequestValidationError,
        http_exception_type=HTTPException,
    )

    @app_obj.middleware("http")
    async def inject_spice_user(request: Request, call_next):  # type: ignore[no-untyped-def]
        role = request.headers.get("X-Test-Role", "PO")
        user_id = int(request.headers.get("X-Test-User-Id", str(ORGANIZER_ID)))
        suite = request.headers.get("X-Test-Suite", "mob")
        request.state.spice_user = SpiceUserContext.model_validate(
            {
                "id": user_id,
                "username": "test_user",
                "tenantId": TEST_TENANT_ID,
                "organizationIds": [TEST_TENANT_ID],
                "roles": [{"name": role, "suiteAccessName": suite}],
            }
        )
        request.state.selected_tenant_id = TEST_TENANT_ID
        return await call_next(request)

    api_router = APIRouter(prefix=get_settings().api_root_path_normalized)
    api_router.include_router(dashboard_router)
    app_obj.include_router(api_router)

    ch_mock = MagicMock()
    ch_mock.query_rows = AsyncMock(return_value=[])
    app_obj.dependency_overrides[get_clickhouse_client] = lambda: ch_mock

    session_mock = MagicMock()
    app_obj.dependency_overrides[get_db] = lambda: session_mock

    service_mock = AsyncMock(
        return_value=TeamActivityResponse(
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            summary=TeamActivitySummary(
                total_users=2,
                active_users=1,
                non_active_users=1,
                users_completed_module=1,
                users_chatbot_engaged=1,
            ),
            members=[],
            focus_user_id=None,
            total_users=2,
            total_members=0,
            total_pages=1,
            limit=50,
            offset=0,
            server_time_utc="2026-01-31T00:00:00+00:00",
        )
    )
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.TeamActivityService.get_team_activity",
        service_mock,
    )
    app_obj.state.team_activity_service_mock = service_mock

    questions_mock = AsyncMock(
        return_value=TeamMemberQuestionsResponse(
            user_id=SK_ID,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            questions=[
                TeamMemberQuestionItem(
                    question="How do I measure RR?",
                    occurrence_count=2,
                    last_asked_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
                )
            ],
            total_questions=1,
            total_pages=1,
            limit=50,
            offset=0,
            server_time_utc="2026-01-31T00:00:00+00:00",
        )
    )
    monkeypatch.setattr(
        "platform_service.services.team_activity_service.TeamActivityService.get_member_questions",
        questions_mock,
    )
    app_obj.state.member_questions_mock = questions_mock

    yield app_obj
    app_obj.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestTeamActivityRoute:
    async def test_organizer_returns_team_activity(self, client: AsyncClient, app: FastAPI) -> None:
        """PO device principal: scoped viewer uses JWT user id."""
        resp = await client.get(
            platform_path("/dashboard/team-activity"),
            params={"from_date": "2026-01-01", "to_date": "2026-01-31"},
            headers={"X-Test-Role": "PO", "X-Test-User-Id": str(ORGANIZER_ID)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["total_users"] == 2
        assert data["summary"]["active_users"] == 1
        assert "members" in data
        assert "program_organizers" not in data
        service_mock = app.state.team_activity_service_mock
        service_mock.assert_awaited_once()
        scope = service_mock.await_args.kwargs["scope"]
        assert scope == TeamActivityScope(viewer_id=ORGANIZER_ID, unrestricted=False)
        assert service_mock.await_args.kwargs["focus_user_id"] is None

    async def test_area_manager_scoped(
        self, client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "platform_service.auth.spice_identity.org_user_index",
            AsyncMock(
                return_value={
                    AM_ID: _org_user(AM_ID, role=HierarchyRole.AREA_MANAGER.value, name="AM"),
                }
            ),
        )
        resp = await client.get(
            platform_path("/dashboard/team-activity"),
            params={"from_date": "2026-01-01", "to_date": "2026-01-31"},
            headers={
                "X-Test-Role": "AREA_MANAGER",
                "X-Test-User-Id": str(AM_ID),
                "X-Test-Suite": "admin",
            },
        )
        assert resp.status_code == 200
        scope = app.state.team_activity_service_mock.await_args.kwargs["scope"]
        assert scope == TeamActivityScope(viewer_id=AM_ID, unrestricted=False)

    async def test_platform_admin_unrestricted(self, client: AsyncClient, app: FastAPI) -> None:
        resp = await client.get(
            platform_path("/dashboard/team-activity"),
            params={"from_date": "2026-01-01", "to_date": "2026-01-31"},
            headers={
                "X-Test-Role": "head office",
                "X-Test-User-Id": "999",
                "X-Test-Suite": "admin",
            },
        )
        assert resp.status_code == 200
        scope = app.state.team_activity_service_mock.await_args.kwargs["scope"]
        assert scope == TeamActivityScope(viewer_id=999, unrestricted=True)

    async def test_auth_disabled_unrestricted(
        self, client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When Spice auth is off, scope is unrestricted."""
        settings = get_settings().model_copy(update={"spice_auth_enabled": False})
        monkeypatch.setattr("platform_service.auth.spice_identity.get_settings", lambda: settings)
        resp = await client.get(
            platform_path("/dashboard/team-activity"),
            params={"from_date": "2026-01-01", "to_date": "2026-01-31"},
        )
        assert resp.status_code == 200
        service_mock = app.state.team_activity_service_mock
        service_mock.assert_awaited_once()
        scope = service_mock.await_args.kwargs["scope"]
        assert scope == TeamActivityScope(viewer_id=None, unrestricted=True)

    async def test_user_id_query_forwarded(self, client: AsyncClient, app: FastAPI) -> None:
        resp = await client.get(
            platform_path("/dashboard/team-activity"),
            params={
                "from_date": "2026-01-01",
                "to_date": "2026-01-31",
                "user_id": AM_ID,
            },
            headers={
                "X-Test-Role": "head office",
                "X-Test-User-Id": "999",
                "X-Test-Suite": "admin",
            },
        )
        assert resp.status_code == 200
        assert app.state.team_activity_service_mock.await_args.kwargs["focus_user_id"] == AM_ID

    async def test_out_of_subtree_user_id_returns_403(self, client: AsyncClient, app: FastAPI) -> None:
        app.state.team_activity_service_mock.side_effect = AppError(
            ErrorCode.FORBIDDEN.value,
            "user_id is outside the caller's team hierarchy",
            status=403,
        )
        resp = await client.get(
            platform_path("/dashboard/team-activity"),
            params={
                "from_date": "2026-01-01",
                "to_date": "2026-01-31",
                "user_id": AM_ID,
            },
            headers={"X-Test-Role": "PO", "X-Test-User-Id": str(ORGANIZER_ID)},
        )
        assert resp.status_code == 403

    async def test_non_organizer_forbidden(self, client: AsyncClient) -> None:
        resp = await client.get(
            platform_path("/dashboard/team-activity"),
            params={"from_date": "2026-01-01", "to_date": "2026-01-31"},
            headers={"X-Test-Role": "SHASTIYA_KORMI", "X-Test-User-Id": str(SK_ID)},
        )
        assert resp.status_code == 403

    async def test_invalid_date_range_returns_422(self, client: AsyncClient) -> None:
        resp = await client.get(
            platform_path("/dashboard/team-activity"),
            params={"from_date": "2026-02-01", "to_date": "2026-01-01"},
            headers={"X-Test-Role": "PO", "X-Test-User-Id": str(ORGANIZER_ID)},
        )
        assert resp.status_code == 422

    async def test_pagination_params_passed(self, client: AsyncClient, app: FastAPI) -> None:
        resp = await client.get(
            platform_path("/dashboard/team-activity"),
            params={
                "from_date": "2026-01-01",
                "to_date": "2026-01-31",
                "limit": 10,
                "offset": 5,
            },
            headers={"X-Test-Role": "PO", "X-Test-User-Id": str(ORGANIZER_ID)},
        )
        assert resp.status_code == 200
        service_mock = app.state.team_activity_service_mock
        service_mock.assert_awaited_once()
        call_kwargs = service_mock.await_args.kwargs
        assert call_kwargs["limit"] == 10
        assert call_kwargs["offset"] == 5

    async def test_depth_query_forwarded(self, client: AsyncClient, app: FastAPI) -> None:
        resp = await client.get(
            platform_path("/dashboard/team-activity"),
            params={
                "from_date": "2026-01-01",
                "to_date": "2026-01-31",
                "depth": 2,
            },
            headers={
                "X-Test-Role": "head office",
                "X-Test-User-Id": "999",
                "X-Test-Suite": "admin",
            },
        )
        assert resp.status_code == 200
        assert app.state.team_activity_service_mock.await_args.kwargs["depth"] == 2

    async def test_depth_default_is_zero(self, client: AsyncClient, app: FastAPI) -> None:
        resp = await client.get(
            platform_path("/dashboard/team-activity"),
            params={"from_date": "2026-01-01", "to_date": "2026-01-31"},
            headers={
                "X-Test-Role": "head office",
                "X-Test-User-Id": "999",
                "X-Test-Suite": "admin",
            },
        )
        assert resp.status_code == 200
        assert app.state.team_activity_service_mock.await_args.kwargs["depth"] == 0

    async def test_depth_out_of_range_returns_422(self, client: AsyncClient) -> None:
        resp = await client.get(
            platform_path("/dashboard/team-activity"),
            params={
                "from_date": "2026-01-01",
                "to_date": "2026-01-31",
                "depth": 3,
            },
            headers={
                "X-Test-Role": "head office",
                "X-Test-User-Id": "999",
                "X-Test-Suite": "admin",
            },
        )
        assert resp.status_code == 422

    async def test_illegal_depth_for_focus_returns_422(
        self, client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "platform_service.auth.spice_identity.org_user_index",
            AsyncMock(
                return_value={
                    AM_ID: _org_user(AM_ID, role=HierarchyRole.AREA_MANAGER.value, name="AM"),
                }
            ),
        )
        app.state.team_activity_service_mock.side_effect = AppError(
            ErrorCode.VALIDATION_ERROR.value,
            "depth=2 is not valid for the effective focus role",
            status=422,
        )
        resp = await client.get(
            platform_path("/dashboard/team-activity"),
            params={
                "from_date": "2026-01-01",
                "to_date": "2026-01-31",
                "depth": 2,
            },
            headers={
                "X-Test-Role": "AREA_MANAGER",
                "X-Test-User-Id": str(AM_ID),
                "X-Test-Suite": "admin",
            },
        )
        assert resp.status_code == 422


class TestTeamMemberQuestionsRoute:
    async def test_organizer_returns_member_questions(self, client: AsyncClient, app: FastAPI) -> None:
        resp = await client.get(
            platform_path(f"/dashboard/team-activity/users/{SK_ID}/questions"),
            params={"from_date": "2026-01-01", "to_date": "2026-01-31"},
            headers={"X-Test-Role": "PO", "X-Test-User-Id": str(ORGANIZER_ID)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == SK_ID
        assert data["total_questions"] == 1
        assert data["questions"][0]["question"] == "How do I measure RR?"
        assert data["questions"][0]["occurrence_count"] == 2
        questions_mock = app.state.member_questions_mock
        questions_mock.assert_awaited_once()
        call_kwargs = questions_mock.await_args.kwargs
        assert call_kwargs["scope"] == TeamActivityScope(viewer_id=ORGANIZER_ID, unrestricted=False)
        assert call_kwargs["user_id"] == SK_ID

    async def test_admin_forwards_unrestricted_scope(self, client: AsyncClient, app: FastAPI) -> None:
        resp = await client.get(
            platform_path(f"/dashboard/team-activity/users/{SK_ID}/questions"),
            params={"from_date": "2026-01-01", "to_date": "2026-01-31"},
            headers={
                "X-Test-Role": "head office",
                "X-Test-User-Id": "999",
                "X-Test-Suite": "admin",
            },
        )
        assert resp.status_code == 200
        call_kwargs = app.state.member_questions_mock.await_args.kwargs
        assert call_kwargs["scope"] == TeamActivityScope(viewer_id=999, unrestricted=True)
        assert call_kwargs["user_id"] == SK_ID

    async def test_area_manager_forwards_scoped_viewer(
        self, client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "platform_service.auth.spice_identity.org_user_index",
            AsyncMock(
                return_value={
                    AM_ID: _org_user(AM_ID, role=HierarchyRole.AREA_MANAGER.value, name="AM"),
                }
            ),
        )
        resp = await client.get(
            platform_path(f"/dashboard/team-activity/users/{SK_ID}/questions"),
            params={"from_date": "2026-01-01", "to_date": "2026-01-31"},
            headers={
                "X-Test-Role": "AREA_MANAGER",
                "X-Test-User-Id": str(AM_ID),
                "X-Test-Suite": "admin",
            },
        )
        assert resp.status_code == 200
        call_kwargs = app.state.member_questions_mock.await_args.kwargs
        assert call_kwargs["scope"] == TeamActivityScope(viewer_id=AM_ID, unrestricted=False)
        assert call_kwargs["user_id"] == SK_ID

    async def test_auth_disabled_forwards_unrestricted_scope(
        self, client: AsyncClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = get_settings().model_copy(update={"spice_auth_enabled": False})
        monkeypatch.setattr("platform_service.auth.spice_identity.get_settings", lambda: settings)
        resp = await client.get(
            platform_path(f"/dashboard/team-activity/users/{SK_ID}/questions"),
            params={"from_date": "2026-01-01", "to_date": "2026-01-31"},
        )
        assert resp.status_code == 200
        call_kwargs = app.state.member_questions_mock.await_args.kwargs
        assert call_kwargs["scope"] == TeamActivityScope(viewer_id=None, unrestricted=True)

    async def test_invalid_date_range_returns_422(self, client: AsyncClient) -> None:
        resp = await client.get(
            platform_path(f"/dashboard/team-activity/users/{SK_ID}/questions"),
            params={"from_date": "2026-02-01", "to_date": "2026-01-01"},
            headers={"X-Test-Role": "PO", "X-Test-User-Id": str(ORGANIZER_ID)},
        )
        assert resp.status_code == 422

    async def test_off_team_forbidden(self, client: AsyncClient, app: FastAPI) -> None:
        app.state.member_questions_mock.side_effect = AppError(
            ErrorCode.FORBIDDEN.value,
            "user_id is outside the caller's team hierarchy",
            status=403,
        )
        resp = await client.get(
            platform_path(f"/dashboard/team-activity/users/{SK_ID}/questions"),
            params={"from_date": "2026-01-01", "to_date": "2026-01-31"},
            headers={"X-Test-Role": "PO", "X-Test-User-Id": str(ORGANIZER_ID)},
        )
        assert resp.status_code == 403

    async def test_clickhouse_failure_returns_502(self, client: AsyncClient, app: FastAPI) -> None:
        app.state.member_questions_mock.side_effect = RuntimeError("ch down")
        resp = await client.get(
            platform_path(f"/dashboard/team-activity/users/{SK_ID}/questions"),
            params={"from_date": "2026-01-01", "to_date": "2026-01-31"},
            headers={"X-Test-Role": "PO", "X-Test-User-Id": str(ORGANIZER_ID)},
        )
        assert resp.status_code == 502

    async def test_pagination_params_passed(self, client: AsyncClient, app: FastAPI) -> None:
        resp = await client.get(
            platform_path(f"/dashboard/team-activity/users/{SK_ID}/questions"),
            params={
                "from_date": "2026-01-01",
                "to_date": "2026-01-31",
                "limit": 10,
                "offset": 5,
            },
            headers={"X-Test-Role": "PO", "X-Test-User-Id": str(ORGANIZER_ID)},
        )
        assert resp.status_code == 200
        call_kwargs = app.state.member_questions_mock.await_args.kwargs
        assert call_kwargs["limit"] == 10
        assert call_kwargs["offset"] == 5
