"""Layer 2 chunk 3 — admin_modules API endpoint tests.

Endpoint contract checks on top of the chunk-2 ModuleRepository tests.
We mostly verify:

- HTTP-level URL → repo call → response shape correctness.
- Pydantic response models serialise the way the FE expects (visibility
  window bounds, ISO timestamps for clinically_reviewed_at, quality_flags).
- 404 error paths.
- Trigger-binding CRUD round-trips.
- Ingestion-run list/detail include steps in the right order.

Test isolation: an autouse function-scoped fixture truncates the data
tables between tests (the API endpoints commit, so cross-test leak is the
default unless we wipe).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from asyncpg import Range
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from platform_service.api.admin_modules import router as admin_modules_router
from platform_service.db.models.ingestion_run import IngestionRun, IngestionRunStep
from platform_service.db.models.module import Module
from platform_service.db.models.module_family import ModuleFamily
from platform_service.db.models.module_quiz_question import ModuleQuizQuestion
from platform_service.db.models.source_document import SourceDocument
from platform_service.db.models.trigger_definition import (
    ModuleTriggerBinding,
    TriggerDefinition,
)
from platform_service.deps import get_db
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio]


# ─── Per-test cleanup ──────────────────────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def _wipe_data_between_tests(db_session: AsyncSession) -> AsyncIterator[None]:
    """The endpoints commit, so committed state from a prior test would leak.
    Truncate the tables this file touches before each test."""
    yield
    # Fresh transaction for the truncate.
    await db_session.rollback()
    await db_session.execute(
        text(
            "TRUNCATE module_quiz_question, module, module_family, "
            "module_trigger_binding, trigger_definition, "
            "ingestion_run_step, ingestion_run, source_document "
            "RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()


# ─── App + client fixtures ─────────────────────────────────────────────────


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    """Build a minimal FastAPI app with the admin_modules router and
    dependency-override `get_db` to share the test session."""
    app_obj = FastAPI()
    app_obj.include_router(admin_modules_router)

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


# ─── Helpers ────────────────────────────────────────────────────────────────


async def _seed_module(
    session: AsyncSession,
    *,
    title_bn: str = "Sample",
    title_en: str | None = None,
    domain: str = "rmnch",
    lifecycle_status: str = "published",
    clinically_reviewed: bool = False,
    visibility_window: Range | None = None,
    embedding: list[float] | None = None,
    module_json: dict | None = None,
    quality_flags_jsonb: dict | None = None,
    set_family_pointer: bool = True,
) -> Module:
    family = ModuleFamily(module_code=f"f-{uuid4().hex[:8]}")
    session.add(family)
    await session.flush()
    module = Module(
        module_family_id=family.id,
        version=1,
        title_bn=title_bn,
        title_en=title_en,
        domain=domain,
        module_type="refresher",
        lifecycle_status=lifecycle_status,
        clinically_reviewed=clinically_reviewed,
        visibility_window=visibility_window,
        embedding=embedding,
        module_json=module_json or {"cards": [{"title_bn": "C1", "body_bn": "B1"}]},
        quality_flags_jsonb=quality_flags_jsonb,
        published_at=datetime.now(UTC) if lifecycle_status == "published" else None,
    )
    session.add(module)
    await session.flush()
    if set_family_pointer and lifecycle_status == "published":
        family.current_published_module_id = module.id
        await session.flush()
    await session.commit()
    return module


def _zero_vector(dim: int = 768) -> list[float]:
    return [0.0] * dim


def _unit_basis_vector(axis: int, dim: int = 768) -> list[float]:
    v = [0.0] * dim
    v[axis % dim] = 1.0
    return v


# ─── GET /admin/modules ────────────────────────────────────────────────────


class TestListModules:
    async def test_returns_summaries(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await _seed_module(db_session, title_bn="Module A")
        await _seed_module(db_session, title_bn="Module B")

        resp = await client.get("/admin/modules")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        sample = data[0]
        # Summary shape: must NOT include cards or quiz (those are detail-only).
        assert "cards" not in sample
        assert "quiz" not in sample
        assert {"id", "title_bn", "card_count", "lifecycle_status", "clinically_reviewed"} <= set(sample)

    async def test_card_count_reflects_module_json(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_module(
            db_session,
            module_json={"cards": [{"title_bn": "1"}, {"title_bn": "2"}, {"title_bn": "3"}]},
        )
        resp = await client.get("/admin/modules")
        assert resp.json()[0]["card_count"] == 3

    async def test_status_filter(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await _seed_module(db_session, title_bn="live")
        await _seed_module(db_session, title_bn="gone", lifecycle_status="retired", set_family_pointer=False)

        # Default excludes retired.
        default_resp = await client.get("/admin/modules")
        titles = {m["title_bn"] for m in default_resp.json()}
        assert "live" in titles and "gone" not in titles

        # Explicit retired filter shows only retired.
        retired_resp = await client.get("/admin/modules?status=retired")
        titles = {m["title_bn"] for m in retired_resp.json()}
        assert titles == {"gone"}

    async def test_clinically_reviewed_filter(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await _seed_module(db_session, title_bn="reviewed", clinically_reviewed=True)
        await _seed_module(db_session, title_bn="pending", clinically_reviewed=False)

        resp = await client.get("/admin/modules?clinically_reviewed=true")
        titles = {m["title_bn"] for m in resp.json()}
        assert titles == {"reviewed"}

        resp = await client.get("/admin/modules?clinically_reviewed=false")
        titles = {m["title_bn"] for m in resp.json()}
        assert titles == {"pending"}

    async def test_full_text_query_filter(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await _seed_module(db_session, title_bn="Pregnancy referral")
        await _seed_module(db_session, title_bn="Diabetes screening")

        resp = await client.get("/admin/modules?q=referral")
        titles = {m["title_bn"] for m in resp.json()}
        assert titles == {"Pregnancy referral"}

    async def test_has_visibility_window_filter(self, client: AsyncClient, db_session: AsyncSession) -> None:
        now = datetime.now(UTC)
        await _seed_module(
            db_session,
            title_bn="windowed",
            visibility_window=Range(now, now + timedelta(days=7), lower_inc=True, upper_inc=False),
        )
        await _seed_module(db_session, title_bn="no-window")

        resp = await client.get("/admin/modules?has_visibility_window=true")
        assert {m["title_bn"] for m in resp.json()} == {"windowed"}

        resp = await client.get("/admin/modules?has_visibility_window=false")
        assert {m["title_bn"] for m in resp.json()} == {"no-window"}

    async def test_pagination_limit_offset(self, client: AsyncClient, db_session: AsyncSession) -> None:
        for i in range(5):
            await _seed_module(db_session, title_bn=f"m{i}")

        resp = await client.get("/admin/modules?limit=2&offset=0")
        assert len(resp.json()) == 2
        resp = await client.get("/admin/modules?limit=2&offset=2")
        assert len(resp.json()) == 2
        resp = await client.get("/admin/modules?limit=2&offset=4")
        assert len(resp.json()) == 1

    async def test_limit_validation_rejects_zero(self, client: AsyncClient, db_session: AsyncSession) -> None:
        resp = await client.get("/admin/modules?limit=0")
        assert resp.status_code == 422

    async def test_limit_validation_rejects_excessive(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await client.get("/admin/modules?limit=500")
        assert resp.status_code == 422

    async def test_quality_flags_surfaced_in_summary(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        flags = {"flags": ["insufficient_tokens"]}
        await _seed_module(db_session, title_bn="flagged", quality_flags_jsonb=flags)
        await _seed_module(db_session, title_bn="clean", quality_flags_jsonb=None)

        resp = await client.get("/admin/modules")
        rows = {m["title_bn"]: m for m in resp.json()}
        assert rows["flagged"]["quality_flags"] == flags
        assert rows["clean"]["quality_flags"] is None

    async def test_has_quality_flags_filter(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await _seed_module(
            db_session,
            title_bn="flagged",
            quality_flags_jsonb={"flags": ["insufficient_tokens"]},
        )
        await _seed_module(db_session, title_bn="clean-null", quality_flags_jsonb=None)
        # Empty dict should be treated as "no flags".
        await _seed_module(db_session, title_bn="clean-empty", quality_flags_jsonb={})

        resp = await client.get("/admin/modules?has_quality_flags=true")
        assert {m["title_bn"] for m in resp.json()} == {"flagged"}

        resp = await client.get("/admin/modules?has_quality_flags=false")
        assert {m["title_bn"] for m in resp.json()} == {"clean-null", "clean-empty"}


# ─── GET /admin/modules/{id} ───────────────────────────────────────────────


class TestGetModuleDetail:
    async def test_returns_full_payload(self, client: AsyncClient, db_session: AsyncSession) -> None:
        m = await _seed_module(
            db_session,
            module_json={"cards": [{"title_bn": "C1", "body_bn": "B1"}]},
        )

        resp = await client.get(f"/admin/modules/{m.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(m.id)
        assert data["title_bn"] == "Sample"
        assert isinstance(data["cards"], list)
        assert isinstance(data["quiz"], list)
        assert data["cards"][0]["title_bn"] == "C1"
        # Detail-only fields are present.
        assert "difficulty_level" in data
        assert "pass_threshold_override" in data

    async def test_quiz_join_orders_by_question_order(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        m = await _seed_module(db_session)
        # Insert in reverse order; response should be 1, 2, 3.
        for order in (3, 1, 2):
            db_session.add(
                ModuleQuizQuestion(
                    module_id=m.id,
                    question_order=order,
                    question_family_id=uuid4(),
                    question_version=1,
                    question_bn=f"Q{order}",
                    options_bn=["a", "b", "c", "d"],
                    correct_indices=[0],
                )
            )
        await db_session.commit()

        resp = await client.get(f"/admin/modules/{m.id}")
        quiz = resp.json()["quiz"]
        assert [q["question_order"] for q in quiz] == [1, 2, 3]

    async def test_returns_404_for_missing(self, client: AsyncClient) -> None:
        resp = await client.get(f"/admin/modules/{uuid4()}")
        assert resp.status_code == 404

    async def test_visibility_window_serialised_with_lower_upper(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        starts = datetime(2026, 6, 1, tzinfo=UTC)
        ends = datetime(2026, 6, 30, tzinfo=UTC)
        m = await _seed_module(
            db_session,
            visibility_window=Range(starts, ends, lower_inc=True, upper_inc=False),
        )
        resp = await client.get(f"/admin/modules/{m.id}")
        data = resp.json()
        # ISO 8601 with Z or +00:00 — accept both.
        lower = data["visibility_window_lower"]
        upper = data["visibility_window_upper"]
        assert lower is not None
        assert upper is not None
        assert "2026-06-01" in lower
        assert "2026-06-30" in upper

    async def test_null_visibility_window_serialises_as_null(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        m = await _seed_module(db_session, visibility_window=None)
        resp = await client.get(f"/admin/modules/{m.id}")
        data = resp.json()
        assert data["visibility_window_lower"] is None
        assert data["visibility_window_upper"] is None
        assert data["has_visibility_window"] is False


# ─── PUT /admin/modules/{id} ───────────────────────────────────────────────


class TestEditModule:
    async def test_creates_new_version(self, client: AsyncClient, db_session: AsyncSession) -> None:
        v1 = await _seed_module(db_session, title_bn="v1 title")

        resp = await client.put(
            f"/admin/modules/{v1.id}",
            json={"title_bn": "v2 title"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["module_family_id"] == str(v1.module_family_id)
        assert body["version"] == 2
        assert body["supersedes_module_id"] == str(v1.id)
        # v2 has its own module id, distinct from v1.
        assert body["id"] != str(v1.id)

    async def test_adds_quiz_questions(self, client: AsyncClient, db_session: AsyncSession) -> None:
        v1 = await _seed_module(db_session, title_bn="v1 title")

        resp = await client.put(
            f"/admin/modules/{v1.id}",
            json={
                "title_bn": "v2 title",
                "quiz": [
                    {
                        "question_bn": "Q1 Bangla",
                        "options_bn": ["A", "B", "C", "D"],
                        "correct_indices": [0],
                    },
                    {
                        "question_bn": "Q2 Bangla",
                        "options_bn": ["W", "X", "Y", "Z"],
                        "correct_indices": [1],
                    },
                ],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        new_module_id = body["id"]

        # Verify questions were created
        from platform_service.db.models.module_quiz_question import ModuleQuizQuestion
        from sqlalchemy import select

        # Need to use a fresh session or refresh to see the changes committed by the endpoint
        # Wait, the endpoint commits, so we should be able to see it in db_session if we don't use cache.
        # Let's use a select statement.
        stmt = select(ModuleQuizQuestion).where(ModuleQuizQuestion.module_id == UUID(new_module_id))
        result = await db_session.execute(stmt)
        questions = result.scalars().all()
        assert len(questions) == 2
        # Order might be by id or question_order. We didn't specify question_order in request,
        # so it defaults to index (1, 2).
        # Let's check by question_bn to be safe.
        q_bns = {q.question_bn for q in questions}
        assert q_bns == {"Q1 Bangla", "Q2 Bangla"}

    async def test_updates_existing_quiz_question(self, client: AsyncClient, db_session: AsyncSession) -> None:
        v1 = await _seed_module(db_session, title_bn="v1 title")
        
        # Create a question for v1
        from platform_service.db.models.module_quiz_question import ModuleQuizQuestion
        q1 = ModuleQuizQuestion(
            module_id=v1.id,
            question_order=1,
            question_family_id=uuid4(),
            question_version=1,
            question_bn="Q1 Original",
            options_bn=["A", "B", "C", "D"],
            correct_indices=[0],
        )
        db_session.add(q1)
        await db_session.commit()

        resp = await client.put(
            f"/admin/modules/{v1.id}",
            json={
                "title_bn": "v2 title",
                "quiz": [
                    {
                        "id": str(q1.id),
                        "question_bn": "Q1 Updated",
                        "options_bn": ["A", "B", "C", "D"],
                        "correct_indices": [0],
                    },
                ],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        new_module_id = body["id"]

        # Verify question was updated (new row with same family, incremented version)
        from sqlalchemy import select

        stmt = select(ModuleQuizQuestion).where(ModuleQuizQuestion.module_id == UUID(new_module_id))
        result = await db_session.execute(stmt)
        questions = result.scalars().all()
        assert len(questions) == 1
        assert questions[0].question_bn == "Q1 Updated"
        assert questions[0].question_family_id == q1.question_family_id
        assert questions[0].question_version == 2

    async def test_adds_quiz_questions_from_module_json(self, client: AsyncClient, db_session: AsyncSession) -> None:
        v1 = await _seed_module(db_session, title_bn="v1 title")

        resp = await client.put(
            f"/admin/modules/{v1.id}",
            json={
                "title_bn": "v2 title",
                "module_json": {
                    "cards": [],
                    "quiz": [
                        {
                            "question_en": "Test question from json",
                            "options_bn": ["A"],
                            "correct_indices": [0],
                        }
                    ]
                }
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        new_module_id = body["id"]

        # Verify questions were created
        from platform_service.db.models.module_quiz_question import ModuleQuizQuestion
        from sqlalchemy import select

        stmt = select(ModuleQuizQuestion).where(ModuleQuizQuestion.module_id == UUID(new_module_id))
        result = await db_session.execute(stmt)
        questions = result.scalars().all()
        assert len(questions) == 1
        assert questions[0].question_en == "Test question from json"
        assert questions[0].question_bn == ""  # Fallback handled

    async def test_returns_404_for_unknown(self, client: AsyncClient) -> None:
        resp = await client.put(
            f"/admin/modules/{uuid4()}",
            json={"title_bn": "noop"},
        )
        assert resp.status_code == 404

    async def test_returns_404_for_retired(self, client: AsyncClient, db_session: AsyncSession) -> None:
        m = await _seed_module(db_session, lifecycle_status="retired", set_family_pointer=False)
        resp = await client.put(f"/admin/modules/{m.id}", json={"title_bn": "won't take"})
        assert resp.status_code == 404


# ─── POST /admin/modules/{id}/clinically-reviewed ──────────────────────────


class TestClinicallyReviewedEndpoint:
    async def test_flips_flag_to_true_with_audit(self, client: AsyncClient, db_session: AsyncSession) -> None:
        m = await _seed_module(db_session, clinically_reviewed=False)
        reviewer = uuid4()

        resp = await client.post(
            f"/admin/modules/{m.id}/clinically-reviewed",
            json={"clinically_reviewed": True, "reviewer_id": str(reviewer)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["clinically_reviewed"] is True
        assert data["clinically_reviewed_at"] is not None
        assert data["clinically_reviewed_by"] == str(reviewer)

    async def test_flips_flag_to_false_clears_audit(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        m = await _seed_module(db_session, clinically_reviewed=True)
        # Pre-populate the audit fields.
        m.clinically_reviewed_at = datetime.now(UTC)
        m.clinically_reviewed_by = uuid4()
        await db_session.commit()

        resp = await client.post(
            f"/admin/modules/{m.id}/clinically-reviewed",
            json={"clinically_reviewed": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["clinically_reviewed"] is False
        assert data["clinically_reviewed_at"] is None
        assert data["clinically_reviewed_by"] is None

    async def test_returns_404_for_unknown(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"/admin/modules/{uuid4()}/clinically-reviewed",
            json={"clinically_reviewed": True},
        )
        assert resp.status_code == 404


# ─── POST /admin/modules/{id}/visibility-window ────────────────────────────


class TestVisibilityWindowEndpoint:
    async def test_set_window_with_iso_timestamps(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        m = await _seed_module(db_session)

        resp = await client.post(
            f"/admin/modules/{m.id}/visibility-window",
            json={
                "starts_at": "2026-06-01T00:00:00Z",
                "ends_at": "2026-06-30T00:00:00Z",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["visibility_window"] is not None
        assert "2026-06-01" in data["visibility_window"]["lower"]
        assert "2026-06-30" in data["visibility_window"]["upper"]

    async def test_clear_window_with_nulls(self, client: AsyncClient, db_session: AsyncSession) -> None:
        now = datetime.now(UTC)
        m = await _seed_module(
            db_session,
            visibility_window=Range(now, now + timedelta(days=7), lower_inc=True, upper_inc=False),
        )

        resp = await client.post(
            f"/admin/modules/{m.id}/visibility-window",
            json={"starts_at": None, "ends_at": None},
        )
        assert resp.status_code == 200
        assert resp.json()["visibility_window"] is None

    async def test_returns_404_for_unknown(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"/admin/modules/{uuid4()}/visibility-window",
            json={"starts_at": None, "ends_at": None},
        )
        assert resp.status_code == 404


# ─── DELETE /admin/modules/{id} (retire) ───────────────────────────────────


class TestRetireEndpoint:
    async def test_delete_retires_module(self, client: AsyncClient, db_session: AsyncSession) -> None:
        m = await _seed_module(db_session, title_bn="bye")

        resp = await client.delete(f"/admin/modules/{m.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["lifecycle_status"] == "retired"
        assert data["deprecated_at"] is not None

    async def test_delete_unknown_returns_404(self, client: AsyncClient) -> None:
        resp = await client.delete(f"/admin/modules/{uuid4()}")
        assert resp.status_code == 404


# ─── POST /admin/modules/search (semantic) ────────────────────────────────


class TestSemanticSearch:
    async def test_top_k_modules_by_cosine_distance(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        a = await _seed_module(db_session, title_bn="A", embedding=_unit_basis_vector(0))
        await _seed_module(db_session, title_bn="B", embedding=_unit_basis_vector(1))
        await _seed_module(db_session, title_bn="C", embedding=_unit_basis_vector(2))

        resp = await client.post(
            "/admin/modules/search",
            json={"query_vector": _unit_basis_vector(0), "limit": 3},
        )
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 3
        # Module A is rank 1 (cosine distance 0 to query).
        assert results[0]["id"] == str(a.id)

    async def test_skips_modules_without_embedding(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        with_emb = await _seed_module(db_session, title_bn="indexed", embedding=_unit_basis_vector(0))
        await _seed_module(db_session, title_bn="not-indexed", embedding=None)

        resp = await client.post(
            "/admin/modules/search",
            json={"query_vector": _unit_basis_vector(0), "limit": 5},
        )
        ids = {m["id"] for m in resp.json()}
        assert str(with_emb.id) in ids
        # Only one row returned — the unembedded module is skipped.
        assert len(ids) == 1

    async def test_query_string_embeds_via_ai_runtime(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When the body sends `query` instead of `query_vector`, the endpoint
        embeds via ai-runtime and feeds the result into search_by_embedding.
        Mock the AIRuntimeClient.embed call to return a known vector."""
        from unittest.mock import AsyncMock

        from platform_service.integrations import ai_runtime_client as arc

        target = await _seed_module(db_session, title_bn="target", embedding=_unit_basis_vector(0))
        await _seed_module(db_session, title_bn="other", embedding=_unit_basis_vector(1))

        embed_mock = AsyncMock(return_value=[_unit_basis_vector(0)])
        monkeypatch.setattr(arc.AIRuntimeClient, "embed", embed_mock)

        resp = await client.post("/admin/modules/search", json={"query": "any text", "limit": 2})
        assert resp.status_code == 200
        results = resp.json()
        assert results[0]["id"] == str(target.id)
        embed_mock.assert_awaited_once_with(["any text"])

    async def test_search_requires_query_or_vector(self, client: AsyncClient) -> None:
        resp = await client.post("/admin/modules/search", json={"limit": 3})
        assert resp.status_code == 400


# ─── Regenerate quiz / embedding ──────────────────────────────────────────


class TestRegeneratePostPublish:
    async def test_regenerate_quiz_enqueues_celery_task(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from unittest.mock import MagicMock

        from platform_service import celery_tasks

        delay_mock = MagicMock()
        monkeypatch.setattr(celery_tasks.generate_module_quiz_task, "delay", delay_mock)

        m = await _seed_module(db_session)
        resp = await client.post(f"/admin/modules/{m.id}/regenerate-quiz")
        assert resp.status_code == 200
        assert resp.json() == {
            "id": str(m.id),
            "enqueued": "platform.generate_module_quiz",
        }
        delay_mock.assert_called_once_with(str(m.id))

    async def test_regenerate_embedding_enqueues_celery_task(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from unittest.mock import MagicMock

        from platform_service import celery_tasks

        delay_mock = MagicMock()
        monkeypatch.setattr(celery_tasks.generate_module_embedding_task, "delay", delay_mock)

        m = await _seed_module(db_session)
        resp = await client.post(f"/admin/modules/{m.id}/regenerate-embedding")
        assert resp.status_code == 200
        assert resp.json() == {
            "id": str(m.id),
            "enqueued": "platform.generate_module_embedding",
        }
        delay_mock.assert_called_once_with(str(m.id))

    async def test_regenerate_quiz_404_when_module_missing(self, client: AsyncClient) -> None:
        resp = await client.post(f"/admin/modules/{uuid4()}/regenerate-quiz")
        assert resp.status_code == 404

    async def test_regenerate_embedding_404_when_module_missing(self, client: AsyncClient) -> None:
        resp = await client.post(f"/admin/modules/{uuid4()}/regenerate-embedding")
        assert resp.status_code == 404


# ─── Trigger binding endpoints ─────────────────────────────────────────────


class TestTriggerBindings:
    async def _seed_trigger_and_binding(
        self,
        db_session: AsyncSession,
        family_id: UUID,
        *,
        relationship: str = "primary",
        priority_weight: int = 10,
    ) -> tuple[TriggerDefinition, ModuleTriggerBinding]:
        td = TriggerDefinition(
            trigger_kind="gap",
            trigger_code=f"gap:test-{uuid4().hex[:6]}",
            predicate_jsonb={"behavioural_gap_code": "test"},
        )
        db_session.add(td)
        await db_session.flush()
        binding = ModuleTriggerBinding(
            trigger_definition_id=td.id,
            module_family_id=family_id,
            relationship=relationship,
            priority_weight=priority_weight,
        )
        db_session.add(binding)
        await db_session.flush()
        await db_session.commit()
        return td, binding

    async def test_list_by_family(self, client: AsyncClient, db_session: AsyncSession) -> None:
        m = await _seed_module(db_session)
        td, binding = await self._seed_trigger_and_binding(
            db_session, m.module_family_id, relationship="primary", priority_weight=10
        )

        resp = await client.get(f"/admin/trigger-bindings/by-module/{m.module_family_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["module_family_id"] == str(m.module_family_id)
        assert data[0]["trigger_definition_id"] == str(td.id)
        assert data[0]["relationship"] == "primary"
        assert data[0]["priority_weight"] == 10

    async def test_create_binding(self, client: AsyncClient, db_session: AsyncSession) -> None:
        m = await _seed_module(db_session)
        td = TriggerDefinition(
            trigger_kind="gap",
            trigger_code=f"gap:test-{uuid4().hex[:6]}",
            predicate_jsonb={"behavioural_gap_code": "test"},
        )
        db_session.add(td)
        await db_session.commit()

        resp = await client.post(
            "/admin/trigger-bindings",
            json={
                "trigger_definition_id": str(td.id),
                "module_family_id": str(m.module_family_id),
                "relationship": "secondary",
                "priority_weight": 25,
                "notes": "covers refresher cadence",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["relationship"] == "secondary"
        assert data["priority_weight"] == 25
        assert data["notes"] == "covers refresher cadence"

    async def test_create_binding_uses_defaults(self, client: AsyncClient, db_session: AsyncSession) -> None:
        m = await _seed_module(db_session)
        td = TriggerDefinition(
            trigger_kind="gap",
            trigger_code=f"gap:test-{uuid4().hex[:6]}",
            predicate_jsonb={"behavioural_gap_code": "test"},
        )
        db_session.add(td)
        await db_session.commit()

        resp = await client.post(
            "/admin/trigger-bindings",
            json={
                "trigger_definition_id": str(td.id),
                "module_family_id": str(m.module_family_id),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["relationship"] == "primary"
        assert data["priority_weight"] == 10
        assert data["notes"] is None

    async def test_update_binding_priority_weight_only(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        m = await _seed_module(db_session)
        td, binding = await self._seed_trigger_and_binding(
            db_session, m.module_family_id, relationship="primary", priority_weight=10
        )

        # Update only priority_weight; relationship should remain "primary".
        resp = await client.put(
            f"/admin/trigger-bindings/{binding.id}",
            json={"priority_weight": 50},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["priority_weight"] == 50
        assert data["relationship"] == "primary"

    async def test_update_binding_relationship_validated(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        m = await _seed_module(db_session)
        td, binding = await self._seed_trigger_and_binding(db_session, m.module_family_id)
        resp = await client.put(
            f"/admin/trigger-bindings/{binding.id}",
            json={"relationship": "tertiary"},  # not in allowed set
        )
        assert resp.status_code == 400

    async def test_update_binding_404_for_unknown(self, client: AsyncClient) -> None:
        resp = await client.put(
            f"/admin/trigger-bindings/{uuid4()}",
            json={"priority_weight": 99},
        )
        assert resp.status_code == 404

    async def test_delete_binding(self, client: AsyncClient, db_session: AsyncSession) -> None:
        m = await _seed_module(db_session)
        td, binding = await self._seed_trigger_and_binding(db_session, m.module_family_id)

        resp = await client.delete(f"/admin/trigger-bindings/{binding.id}")
        assert resp.status_code == 200
        # And listing again returns no bindings for this family.
        list_resp = await client.get(f"/admin/trigger-bindings/by-module/{m.module_family_id}")
        assert list_resp.json() == []

    async def test_delete_binding_404_for_unknown(self, client: AsyncClient) -> None:
        resp = await client.delete(f"/admin/trigger-bindings/{uuid4()}")
        assert resp.status_code == 404


# ─── Ingestion-run endpoints ───────────────────────────────────────────────


class TestIngestionRunEndpoints:
    async def _seed_run(
        self,
        session: AsyncSession,
        *,
        status: str = "succeeded",
        started_offset_seconds: int = 0,
    ) -> IngestionRun:
        # Need a source_document for the FK.
        sd = SourceDocument(
            title=f"doc-{uuid4().hex[:6]}",
            source_type="pdf",
            primary_language="en",
            authority_kind="official_training",
            authority_label="BRAC",
            original_storage_path="/tmp/test.pdf",
        )
        session.add(sd)
        await session.flush()
        run = IngestionRun(
            source_document_id=sd.id,
            status=status,
            started_at=datetime.now(UTC) + timedelta(seconds=started_offset_seconds),
            completed_at=datetime.now(UTC) if status != "running" else None,
        )
        session.add(run)
        await session.flush()
        await session.commit()
        return run

    async def test_list_orders_by_started_desc(self, client: AsyncClient, db_session: AsyncSession) -> None:
        r1 = await self._seed_run(db_session, started_offset_seconds=0)
        r2 = await self._seed_run(db_session, started_offset_seconds=10)
        r3 = await self._seed_run(db_session, started_offset_seconds=20)

        resp = await client.get("/admin/ingestion-runs")
        ids = [row["id"] for row in resp.json()]
        # Newest-first.
        assert ids == [str(r3.id), str(r2.id), str(r1.id)]

    async def test_list_filters_by_status(self, client: AsyncClient, db_session: AsyncSession) -> None:
        await self._seed_run(db_session, status="succeeded", started_offset_seconds=0)
        await self._seed_run(db_session, status="failed", started_offset_seconds=10)

        resp = await client.get("/admin/ingestion-runs?status=failed")
        statuses = {row["status"] for row in resp.json()}
        assert statuses == {"failed"}

    async def test_detail_includes_steps_in_order(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        run = await self._seed_run(db_session)
        # Add three steps with increasing started_at.
        for i, stage in enumerate(("extract", "module_identify", "card_draft")):
            db_session.add(
                IngestionRunStep(
                    ingestion_run_id=run.id,
                    stage=stage,
                    status="succeeded",
                    started_at=datetime.now(UTC) + timedelta(seconds=i),
                    completed_at=datetime.now(UTC) + timedelta(seconds=i + 1),
                )
            )
        await db_session.commit()

        resp = await client.get(f"/admin/ingestion-runs/{run.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(run.id)
        stages = [s["stage"] for s in data["steps"]]
        assert stages == ["extract", "module_identify", "card_draft"]

    async def test_detail_404_for_unknown(self, client: AsyncClient) -> None:
        resp = await client.get(f"/admin/ingestion-runs/{uuid4()}")
        assert resp.status_code == 404
