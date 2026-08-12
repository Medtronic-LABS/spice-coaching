"""Morning cards API endpoint tests.

Verifies:
- GET /morning/cards with auth disabled returns an empty card list
- GET /morning/cards with auth enabled uses the authenticated CHW id
- GET /morning/cards with auth enabled and no principal returns 401
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from mc_foundation.problem import register_problem_handlers
from platform_service.api.morning import router as morning_router
from platform_service.config import Settings, get_settings
from platform_service.db.models.behavioural_gap import BehaviouralGap
from platform_service.db.models.chw_behavioural_gap_state import CHWBehaviouralGapState
from platform_service.db.models.chw_quiz_question_state import CHWQuizQuestionState
from platform_service.db.models.module import Module
from platform_service.db.models.module_family import ModuleFamily
from platform_service.db.models.module_quiz_question import ModuleQuizQuestion
from platform_service.db.repositories.module_gap_repository import ModuleGapRepository
from platform_service.deps import get_db
from pydantic_settings import SettingsConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import platform_path, requires_db

pytestmark = [requires_db, pytest.mark.asyncio]


def _test_chw_id() -> int:
    return uuid4().int % (10**15) + 1


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    get_settings.cache_clear()
    monkeypatch.setattr(
        Settings,
        "model_config",
        SettingsConfigDict(env_file=None, env_file_encoding="utf-8", extra="ignore"),
    )
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture(autouse=True)
async def _wipe_data_between_tests(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.rollback()
    await db_session.execute(
        text(
            "TRUNCATE chw_behavioural_gap_state, chw_quiz_question_state, "
            "behavioural_gap, module_quiz_question, module, module_family "
            "RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    app_obj = FastAPI()
    register_problem_handlers(
        app_obj,
        validation_error_type=RequestValidationError,
        http_exception_type=HTTPException,
    )

    @app_obj.middleware("http")
    async def mock_auth_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        mock_user_id = request.headers.get("x-mock-user-id")
        if mock_user_id:

            class MockSpiceUser:
                id = int(mock_user_id)

            request.state.spice_user = MockSpiceUser()
        request.state.selected_tenant_id = 0
        return await call_next(request)

    api_router = APIRouter(prefix=get_settings().api_root_path_normalized)
    api_router.include_router(morning_router)
    app_obj.include_router(api_router)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app_obj.dependency_overrides[get_db] = _override_get_db
    yield app_obj
    app_obj.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _make_family(session: AsyncSession) -> ModuleFamily:
    fam = ModuleFamily(module_code=f"MF-{uuid4().hex[:8]}", tenant_id=1)
    session.add(fam)
    await session.flush()
    return fam


async def _make_published_module(
    session: AsyncSession,
    *,
    family: ModuleFamily,
    tenant_id: int | None,
    primary_gap_id: UUID | None = None,
    created_at: datetime | None = None,
    set_family_pointer: bool = True,
) -> Module:
    now = datetime.now(UTC)
    mod = Module(
        module_family_id=family.id,
        version=1,
        title_localized={"bn": "t"},
        domain="rmnch",
        module_type="refresher",
        lifecycle_status="published",
        tenant_id=tenant_id,
        primary_gap_id=primary_gap_id,
        module_json={"cards": [{"title": {"bn": "c"}}]},
        published_at=now,
        created_at=created_at or now,
    )
    session.add(mod)
    await session.flush()
    if primary_gap_id is not None:
        await ModuleGapRepository(session).add_primary_link(mod, behavioural_gap_id=primary_gap_id)
    if set_family_pointer:
        family.current_published_module_id = mod.id
        await session.flush()
    await session.commit()
    return mod


async def _make_gap(session: AsyncSession) -> BehaviouralGap:
    gap = BehaviouralGap(
        gap_code=f"gap_{uuid4().hex[:8]}",
        description="d",
        domain="rmnch",
        detection_rule_jsonb={},
        tenant_id=1,
    )
    session.add(gap)
    await session.flush()
    return gap


class TestMorningCardsEndpoint:
    async def test_auth_disabled_returns_empty_cards(
        self, client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPICE_AUTH_ENABLED", "false")
        get_settings.cache_clear()

        tenant = 0
        base = datetime.now(UTC) - timedelta(days=10)
        for i in range(3):
            fam = await _make_family(db_session)
            await _make_published_module(
                db_session,
                family=fam,
                tenant_id=tenant,
                primary_gap_id=None,
                created_at=base + timedelta(hours=i),
            )

        resp = await client.get(platform_path("/morning/cards"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total_points"] == 0

    async def test_auth_enabled_without_user_returns_401(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPICE_AUTH_ENABLED", "true")
        get_settings.cache_clear()

        resp = await client.get(platform_path("/morning/cards"))
        assert resp.status_code == 401

    async def test_auth_enabled_uses_gap_suggestions_for_principal(
        self, client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPICE_AUTH_ENABLED", "true")
        get_settings.cache_clear()
        monkeypatch.setattr(
            get_settings(),
            "telemetry_behavioural_gap_state_enabled",
            True,
        )

        tenant = 0
        chw_id = _test_chw_id()
        gap = await _make_gap(db_session)
        db_session.add(
            CHWBehaviouralGapState(
                chw_id=chw_id,
                behavioural_gap_id=gap.id,
                tenant_id=tenant,
                status="active",
                severity_current="high",
                occurrence_count=3,
            )
        )
        await db_session.flush()

        fam = await _make_family(db_session)
        mod = await _make_published_module(
            db_session,
            family=fam,
            tenant_id=tenant,
            primary_gap_id=gap.id,
        )

        resp = await client.get(
            platform_path("/morning/cards"),
            headers={"x-mock-user-id": str(chw_id)},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["module_id"] == str(mod.id)
        assert items[0]["module_family_id"] == str(fam.id)
        assert items[0]["source"] == "gap"
        assert items[0]["behavioural_gap_id"] == str(gap.id)

    async def test_auth_enabled_uses_quiz_suggestions_for_principal(
        self, client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPICE_AUTH_ENABLED", "true")
        get_settings.cache_clear()

        tenant = 0
        chw_id = _test_chw_id()
        fam = await _make_family(db_session)
        mod = await _make_published_module(
            db_session,
            family=fam,
            tenant_id=tenant,
            primary_gap_id=None,
        )
        quiz = ModuleQuizQuestion(
            module_id=mod.id,
            question_order=1,
            question_family_id=uuid4(),
            question_version=1,
            question_localized={"bn": "q"},
            question_type="single_select",
            options_localized={"bn": ["a", "b"]},
            correct_indices=[0],
        )
        db_session.add(quiz)
        await db_session.flush()
        db_session.add(
            CHWQuizQuestionState(
                chw_id=chw_id,
                quiz_id=quiz.id,
                module_id=mod.id,
                tenant_id=tenant,
                failed_attempts_count=1,
                status="active",
                last_failed_attempt_at=datetime.now(UTC),
            )
        )
        await db_session.commit()

        resp = await client.get(
            platform_path("/morning/cards"),
            headers={"x-mock-user-id": str(chw_id)},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["module_id"] == str(mod.id)
        assert items[0]["source"] == "quiz"
        assert items[0]["quiz_id"] == str(quiz.id)
