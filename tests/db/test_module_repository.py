"""Layer 2 chunk 2 — ModuleRepository tests.

DB-backed end-to-end of the post-architecture-reset admin repository.
Covers:

- list_modules filters: status (default excludes retired), clinically_reviewed,
  has_visibility_window, domain, full-text query, pagination, ordering.
- get_module / list_quiz_questions ordering.
- search_by_embedding: pgvector cosine distance, NULL-embedding skip,
  retired exclusion.
- edit_module: version bump, supersedes pointer, clinically_reviewed reset,
  family pointer update, copy-forward unchanged fields, retire-then-edit
  rejection.
- set_clinically_reviewed: flag flip + audit-fields populate/clear.
- set_visibility_window: asyncpg.Range roundtrip + clear-with-None.
- retire_module: family pointer cascade to prior published version (or null).
- count_modules: mirrors list-default behaviour.

All tests use the platform's `db_session` fixture so they share the same
per-loop engine as production code (see conftest for the engine-loop fix).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from asyncpg import Range
from platform_service.db.models.module import Module
from platform_service.db.models.module_family import ModuleFamily
from platform_service.db.models.module_quiz_question import ModuleQuizQuestion
from platform_service.db.repositories.module_repository import (
    ModuleNotFoundError,
    ModuleRepository,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db

# All tests in this file need a real Postgres + pgvector + alembic-applied schema.
pytestmark = [requires_db, pytest.mark.asyncio]


# ─── Helpers ────────────────────────────────────────────────────────────────


def _zero_vector(dim: int = 768) -> list[float]:
    return [0.0] * dim


def _unit_basis_vector(axis: int, dim: int = 768) -> list[float]:
    """Sparse unit vector — zero everywhere except `axis`. Cosine-distance
    between two of these is 1.0 if axes differ, 0.0 if same axis."""
    v = [0.0] * dim
    v[axis % dim] = 1.0
    return v


async def _make_family(
    session: AsyncSession,
    *,
    module_code: str | None = None,
) -> ModuleFamily:
    fam = ModuleFamily(module_code=module_code or f"family-{uuid4().hex[:8]}")
    session.add(fam)
    await session.flush()
    return fam


async def _make_module(
    session: AsyncSession,
    *,
    family: ModuleFamily | None = None,
    title_bn: str = "Sample Module",
    title_en: str | None = None,
    description_bn: str | None = "Description",
    domain: str = "rmnch",
    module_type: str = "refresher",
    lifecycle_status: str = "published",
    clinically_reviewed: bool = False,
    visibility_window: Range | None = None,
    embedding: list[float] | None = None,
    module_json: dict[str, Any] | None = None,
    version: int = 1,
    published_at: datetime | None = None,
    set_family_pointer: bool = True,
) -> Module:
    if family is None:
        family = await _make_family(session)
    module = Module(
        module_family_id=family.id,
        version=version,
        title_bn=title_bn,
        title_en=title_en,
        description_bn=description_bn,
        domain=domain,
        module_type=module_type,
        lifecycle_status=lifecycle_status,
        clinically_reviewed=clinically_reviewed,
        visibility_window=visibility_window,
        embedding=embedding,
        module_json=module_json or {"cards": [{"title_bn": "Card 1"}]},
        published_at=published_at or (datetime.now(UTC) if lifecycle_status == "published" else None),
    )
    session.add(module)
    await session.flush()
    if set_family_pointer and lifecycle_status == "published":
        family.current_published_module_id = module.id
        await session.flush()
    return module


# ─── list_modules: filters + ordering ───────────────────────────────────────


class TestListModules:
    async def test_default_excludes_retired(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        await _make_module(db_session, family=fam, title_bn="Live", lifecycle_status="published")
        await _make_module(
            db_session,
            family=fam,
            title_bn="Gone",
            lifecycle_status="retired",
            version=2,
            set_family_pointer=False,
        )

        repo = ModuleRepository(db_session)
        rows = await repo.list_modules()
        titles = {m.title_bn for m in rows if m.module_family_id == fam.id}
        assert "Live" in titles
        assert "Gone" not in titles

    async def test_status_retired_filter_returns_only_retired(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        await _make_module(db_session, family=fam, title_bn="Live")
        await _make_module(
            db_session,
            family=fam,
            title_bn="Gone",
            lifecycle_status="retired",
            version=2,
            set_family_pointer=False,
        )

        repo = ModuleRepository(db_session)
        rows = await repo.list_modules(status="retired")
        titles = {m.title_bn for m in rows if m.module_family_id == fam.id}
        assert titles == {"Gone"}

    async def test_clinically_reviewed_true_filter(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        await _make_module(db_session, family=fam, title_bn="Pending", clinically_reviewed=False)
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn="Approved",
            clinically_reviewed=True,
        )

        repo = ModuleRepository(db_session)
        rows = await repo.list_modules(clinically_reviewed=True)
        titles = {m.title_bn for m in rows}
        assert "Approved" in titles
        assert "Pending" not in titles

    async def test_clinically_reviewed_false_filter(self, db_session: AsyncSession) -> None:
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn="Approved-only",
            clinically_reviewed=True,
        )
        unique_title = f"Pending-{uuid4().hex[:8]}"
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn=unique_title,
            clinically_reviewed=False,
        )

        repo = ModuleRepository(db_session)
        rows = await repo.list_modules(clinically_reviewed=False)
        titles = {m.title_bn for m in rows}
        assert unique_title in titles
        assert "Approved-only" not in titles

    async def test_has_visibility_window_true_filter(self, db_session: AsyncSession) -> None:
        now = datetime.now(UTC)
        unique_title = f"With-window-{uuid4().hex[:8]}"
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn=unique_title,
            visibility_window=Range(now, now + timedelta(days=14), lower_inc=True, upper_inc=False),
        )
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn="No-window",
            visibility_window=None,
        )

        repo = ModuleRepository(db_session)
        rows = await repo.list_modules(has_visibility_window=True)
        titles = {m.title_bn for m in rows}
        assert unique_title in titles
        assert "No-window" not in titles

    async def test_has_visibility_window_false_filter(self, db_session: AsyncSession) -> None:
        now = datetime.now(UTC)
        unique_no = f"No-window-{uuid4().hex[:8]}"
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn="With-window",
            visibility_window=Range(now, now + timedelta(days=14), lower_inc=True, upper_inc=False),
        )
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn=unique_no,
            visibility_window=None,
        )

        repo = ModuleRepository(db_session)
        rows = await repo.list_modules(has_visibility_window=False)
        titles = {m.title_bn for m in rows}
        assert unique_no in titles
        assert "With-window" not in titles

    async def test_domain_filter(self, db_session: AsyncSession) -> None:
        unique_dom = f"ncd-{uuid4().hex[:6]}"
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn="NCD-mod",
            domain=unique_dom,
        )
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn="RMNCH-mod",
            domain="rmnch",
        )

        repo = ModuleRepository(db_session)
        rows = await repo.list_modules(domain=unique_dom)
        assert all(m.domain == unique_dom for m in rows)
        assert any(m.title_bn == "NCD-mod" for m in rows)

    async def test_full_text_query_matches_title_bn(self, db_session: AsyncSession) -> None:
        unique = f"Pregnancy{uuid4().hex[:6]}"
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn=f"Module about {unique}",
        )
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn="Module about diabetes",
        )

        repo = ModuleRepository(db_session)
        rows = await repo.list_modules(full_text_query=unique)
        assert len(rows) == 1
        assert unique in rows[0].title_bn

    async def test_full_text_query_matches_title_en(self, db_session: AsyncSession) -> None:
        marker = f"FollowUp{uuid4().hex[:6]}"
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn="x",
            title_en=f"English {marker} guidance",
        )

        repo = ModuleRepository(db_session)
        rows = await repo.list_modules(full_text_query=marker)
        assert len(rows) == 1

    async def test_full_text_query_matches_description_bn(self, db_session: AsyncSession) -> None:
        marker = f"Eclampsia{uuid4().hex[:6]}"
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn="hypertension",
            description_bn=f"covers {marker} signs",
        )

        repo = ModuleRepository(db_session)
        rows = await repo.list_modules(full_text_query=marker)
        assert len(rows) == 1

    async def test_pagination_offset_and_limit(self, db_session: AsyncSession) -> None:
        # Create a unique domain so we can deterministically isolate this test's rows.
        domain = f"dom-{uuid4().hex[:8]}"
        for i in range(5):
            await _make_module(
                db_session,
                family=await _make_family(db_session),
                title_bn=f"M{i}",
                domain=domain,
                published_at=datetime.now(UTC) + timedelta(seconds=i),
            )

        repo = ModuleRepository(db_session)
        page1 = await repo.list_modules(domain=domain, limit=2, offset=0)
        page2 = await repo.list_modules(domain=domain, limit=2, offset=2)
        page3 = await repo.list_modules(domain=domain, limit=2, offset=4)

        assert len(page1) == 2
        assert len(page2) == 2
        assert len(page3) == 1
        # No row appears on more than one page.
        ids = {m.id for m in page1} | {m.id for m in page2} | {m.id for m in page3}
        assert len(ids) == 5

    async def test_results_ordered_by_published_at_desc(self, db_session: AsyncSession) -> None:
        domain = f"order-{uuid4().hex[:6]}"
        old = datetime.now(UTC) - timedelta(days=1)
        new = datetime.now(UTC)
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn="older",
            domain=domain,
            published_at=old,
        )
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn="newer",
            domain=domain,
            published_at=new,
        )

        repo = ModuleRepository(db_session)
        rows = await repo.list_modules(domain=domain)
        # Newest-first.
        assert rows[0].title_bn == "newer"
        assert rows[1].title_bn == "older"


# ─── get_module / list_quiz_questions ───────────────────────────────────────


class TestGetModule:
    async def test_returns_none_for_missing(self, db_session: AsyncSession) -> None:
        repo = ModuleRepository(db_session)
        assert await repo.get_module(uuid4()) is None

    async def test_returns_existing_row(self, db_session: AsyncSession) -> None:
        m = await _make_module(db_session, family=await _make_family(db_session))
        repo = ModuleRepository(db_session)
        out = await repo.get_module(m.id)
        assert out is not None
        assert out.id == m.id


class TestListQuizQuestions:
    async def test_orders_by_question_order_asc(self, db_session: AsyncSession) -> None:
        m = await _make_module(db_session, family=await _make_family(db_session))
        # Insert in reverse order of question_order; reads should reorder.
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

        repo = ModuleRepository(db_session)
        rows = await repo.list_quiz_questions(m.id)
        assert [r.question_order for r in rows] == [1, 2, 3]

    async def test_returns_empty_for_module_with_no_quiz(self, db_session: AsyncSession) -> None:
        m = await _make_module(db_session, family=await _make_family(db_session))
        repo = ModuleRepository(db_session)
        rows = await repo.list_quiz_questions(m.id)
        assert rows == []

    async def test_does_not_return_questions_from_other_modules(self, db_session: AsyncSession) -> None:
        m1 = await _make_module(db_session, family=await _make_family(db_session))
        m2 = await _make_module(db_session, family=await _make_family(db_session))
        db_session.add(
            ModuleQuizQuestion(
                module_id=m1.id,
                question_order=1,
                question_family_id=uuid4(),
                question_version=1,
                question_bn="for m1",
                options_bn=["a", "b", "c", "d"],
                correct_indices=[0],
            )
        )
        db_session.add(
            ModuleQuizQuestion(
                module_id=m2.id,
                question_order=1,
                question_family_id=uuid4(),
                question_version=1,
                question_bn="for m2",
                options_bn=["a", "b", "c", "d"],
                correct_indices=[0],
            )
        )

        repo = ModuleRepository(db_session)
        rows = await repo.list_quiz_questions(m1.id)
        assert len(rows) == 1
        assert rows[0].question_bn == "for m1"


# ─── search_by_embedding (pgvector cosine distance) ─────────────────────────


class TestSearchByEmbedding:
    async def test_top_k_orders_by_cosine_distance(self, db_session: AsyncSession) -> None:
        # Seed 3 modules with sparse unit vectors on different axes.
        # The query is the unit vector on axis 0 → module A is rank 1.
        a = await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn="A",
            embedding=_unit_basis_vector(0),
        )
        b = await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn="B",
            embedding=_unit_basis_vector(1),
        )
        c = await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn="C",
            embedding=_unit_basis_vector(2),
        )

        repo = ModuleRepository(db_session)
        results = await repo.search_by_embedding(query_vector=_unit_basis_vector(0), limit=3)
        # Filter to only the three rows we seeded so other tests' data
        # doesn't pollute the assertion.
        seeded_ids = {a.id, b.id, c.id}
        ours = [(m, dist) for m, dist in results if m.id in seeded_ids]
        assert len(ours) == 3
        assert ours[0][0].id == a.id, "Module A (same axis as query) should be rank 1"
        # Distance to A should be ~0 (cosine distance of identical vectors).
        assert math.isclose(ours[0][1], 0.0, abs_tol=1e-6)
        # Distance to B and C should be 1.0 (orthogonal).
        for m, dist in ours[1:]:
            assert math.isclose(dist, 1.0, abs_tol=1e-6)

    async def test_skips_modules_without_embedding(self, db_session: AsyncSession) -> None:
        with_emb = await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn="indexed",
            embedding=_unit_basis_vector(0),
        )
        without_emb = await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn="not-indexed",
            embedding=None,
        )

        repo = ModuleRepository(db_session)
        results = await repo.search_by_embedding(query_vector=_unit_basis_vector(0), limit=10)
        ids = {m.id for m, _ in results}
        assert with_emb.id in ids
        assert without_emb.id not in ids

    async def test_excludes_retired_even_when_close(self, db_session: AsyncSession) -> None:
        retired = await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn="retired",
            lifecycle_status="retired",
            embedding=_unit_basis_vector(0),
            set_family_pointer=False,
        )

        repo = ModuleRepository(db_session)
        results = await repo.search_by_embedding(query_vector=_unit_basis_vector(0), limit=10)
        ids = {m.id for m, _ in results}
        assert retired.id not in ids

    async def test_limit_caps_results(self, db_session: AsyncSession) -> None:
        # Seed 5 modules with embeddings; ask for top 2.
        for i in range(5):
            await _make_module(
                db_session,
                family=await _make_family(db_session),
                title_bn=f"M{i}",
                embedding=_unit_basis_vector(i % 10),
            )

        repo = ModuleRepository(db_session)
        results = await repo.search_by_embedding(query_vector=_unit_basis_vector(0), limit=2)
        assert len(results) <= 2


# ─── edit_module: versioning + family pointer + reset flag ─────────────────


class TestEditModule:
    async def test_creates_new_version_with_supersedes_pointer(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, title_bn="v1 title", version=1)

        repo = ModuleRepository(db_session)
        v2 = await repo.edit_module(v1.id, title_bn="v2 title")

        assert v2.id != v1.id
        assert v2.module_family_id == fam.id
        assert v2.version == 2
        assert v2.supersedes_module_id == v1.id
        assert v2.title_bn == "v2 title"

    async def test_resets_clinically_reviewed_to_false(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(
            db_session,
            family=fam,
            clinically_reviewed=True,
        )
        v1.clinically_reviewed_at = datetime.now(UTC)
        v1.clinically_reviewed_by = uuid4()

        repo = ModuleRepository(db_session)
        v2 = await repo.edit_module(v1.id, title_bn="new title")
        # New version starts unreviewed regardless of v1's flag.
        assert v2.clinically_reviewed is False

    async def test_copies_unchanged_fields_forward(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(
            db_session,
            family=fam,
            title_bn="v1",
            description_bn="original desc",
            domain="rmnch",
        )
        v1.estimated_minutes = 15
        v1.difficulty_level = "hard"
        v1.module_type = "content_update"

        repo = ModuleRepository(db_session)
        # Edit ONLY the title.
        v2 = await repo.edit_module(v1.id, title_bn="v2")

        assert v2.title_bn == "v2"
        # Untouched fields copy forward.
        assert v2.description_bn == "original desc"
        assert v2.domain == "rmnch"
        assert v2.estimated_minutes == 15
        assert v2.difficulty_level == "hard"
        assert v2.module_type == "content_update"

    async def test_updates_family_current_pointer(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, title_bn="v1")
        # Verify pointer starts at v1.
        await db_session.refresh(fam)
        assert fam.current_published_module_id == v1.id

        repo = ModuleRepository(db_session)
        v2 = await repo.edit_module(v1.id, title_bn="v2")
        await db_session.refresh(fam)
        assert fam.current_published_module_id == v2.id

    async def test_edit_unknown_module_raises(self, db_session: AsyncSession) -> None:
        repo = ModuleRepository(db_session)
        with pytest.raises(ModuleNotFoundError):
            await repo.edit_module(uuid4(), title_bn="x")

    async def test_previous_version_is_retired_on_edit(self, db_session: AsyncSession) -> None:
        """Without retiring v1, the dashboard's default `?status=published`
        list returns BOTH versions for one family (B1 review finding)."""
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, title_bn="v1")
        assert v1.lifecycle_status == "published"
        assert v1.deprecated_at is None

        repo = ModuleRepository(db_session)
        v2 = await repo.edit_module(v1.id, title_bn="v2")
        await db_session.refresh(v1)

        assert v1.lifecycle_status == "retired"
        assert v1.deprecated_at is not None
        # New version is published.
        assert v2.lifecycle_status == "published"

        # Default list (status=None → excludes retired) returns ONLY v2.
        published = await repo.list_modules()
        ids = [m.id for m in published]
        assert v2.id in ids
        assert v1.id not in ids

    async def test_edit_retired_module_raises(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        m = await _make_module(db_session, family=fam, lifecycle_status="retired", set_family_pointer=False)

        repo = ModuleRepository(db_session)
        with pytest.raises(ModuleNotFoundError):
            await repo.edit_module(m.id, title_bn="post-retire")

    async def test_edit_replaces_module_json_when_provided(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, module_json={"cards": [{"title_bn": "old"}]})

        repo = ModuleRepository(db_session)
        new_cards = {"cards": [{"title_bn": "new1"}, {"title_bn": "new2"}]}
        v2 = await repo.edit_module(v1.id, module_json=new_cards)
        assert v2.module_json == new_cards


# ─── set_clinically_reviewed: flip + audit ─────────────────────────────────


class TestSetClinicallyReviewed:
    async def test_flip_to_true_populates_audit_fields(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        m = await _make_module(db_session, family=fam, clinically_reviewed=False)

        reviewer = uuid4()
        repo = ModuleRepository(db_session)
        out = await repo.set_clinically_reviewed(m.id, flag=True, reviewer_id=reviewer)

        assert out.clinically_reviewed is True
        assert out.clinically_reviewed_at is not None
        assert out.clinically_reviewed_by == reviewer
        assert out.lifecycle_status == "published"
        assert out.published_at is not None

    async def test_flip_to_false_clears_audit_fields(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        m = await _make_module(db_session, family=fam, clinically_reviewed=True)
        m.clinically_reviewed_at = datetime.now(UTC)
        m.clinically_reviewed_by = uuid4()

        repo = ModuleRepository(db_session)
        out = await repo.set_clinically_reviewed(m.id, flag=False)

        assert out.clinically_reviewed is False
        # Audit fields cleared on flip-to-false to avoid showing stale reviewer attribution.
        assert out.clinically_reviewed_at is None
        assert out.clinically_reviewed_by is None

    async def test_set_on_unknown_raises(self, db_session: AsyncSession) -> None:
        repo = ModuleRepository(db_session)
        with pytest.raises(ModuleNotFoundError):
            await repo.set_clinically_reviewed(uuid4(), flag=True)

    async def test_set_on_retired_raises(self, db_session: AsyncSession) -> None:
        m = await _make_module(
            db_session,
            family=await _make_family(db_session),
            lifecycle_status="retired",
            set_family_pointer=False,
        )
        repo = ModuleRepository(db_session)
        with pytest.raises(ModuleNotFoundError):
            await repo.set_clinically_reviewed(m.id, flag=True)


# ─── set_visibility_window: asyncpg.Range roundtrip ────────────────────────


class TestSetVisibilityWindow:
    async def test_set_window_with_asyncpg_range(self, db_session: AsyncSession) -> None:
        m = await _make_module(db_session, family=await _make_family(db_session))

        starts = datetime(2026, 5, 1, tzinfo=UTC)
        ends = datetime(2026, 5, 15, tzinfo=UTC)
        window = Range(starts, ends, lower_inc=True, upper_inc=False)

        repo = ModuleRepository(db_session)
        out = await repo.set_visibility_window(m.id, window=window)

        assert out.visibility_window is not None
        # Verify the asyncpg.Range roundtripped correctly into the
        # TSTZRANGE column. Reading via a raw SQL select bypasses the
        # session's identity-map cache so we know we're seeing actual
        # DB-side state, not the just-set Python attribute.
        from sqlalchemy import text

        row = (
            await db_session.execute(
                text(
                    "SELECT lower(visibility_window) AS lo, upper(visibility_window) AS hi FROM module WHERE id = :id"
                ),
                {"id": m.id},
            )
        ).one()
        assert row.lo == starts
        assert row.hi == ends

    async def test_clear_with_none(self, db_session: AsyncSession) -> None:
        now = datetime.now(UTC)
        m = await _make_module(
            db_session,
            family=await _make_family(db_session),
            visibility_window=Range(now, now + timedelta(days=7), lower_inc=True, upper_inc=False),
        )

        repo = ModuleRepository(db_session)
        out = await repo.set_visibility_window(m.id, window=None)
        assert out.visibility_window is None

    async def test_set_on_unknown_raises(self, db_session: AsyncSession) -> None:
        repo = ModuleRepository(db_session)
        with pytest.raises(ModuleNotFoundError):
            await repo.set_visibility_window(uuid4(), window=None)

    async def test_set_on_retired_raises(self, db_session: AsyncSession) -> None:
        m = await _make_module(
            db_session,
            family=await _make_family(db_session),
            lifecycle_status="retired",
            set_family_pointer=False,
        )
        repo = ModuleRepository(db_session)
        with pytest.raises(ModuleNotFoundError):
            await repo.set_visibility_window(m.id, window=None)


# ─── retire_module: family pointer cascade ─────────────────────────────────


class TestRetireModule:
    async def test_retire_sets_status_and_deprecated_at(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        m = await _make_module(db_session, family=fam)

        repo = ModuleRepository(db_session)
        out = await repo.retire_module(m.id)

        assert out.lifecycle_status == "retired"
        assert out.deprecated_at is not None

    async def test_retire_falls_back_to_prior_published_version(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, title_bn="v1", version=1)
        v2 = await _make_module(
            db_session,
            family=fam,
            title_bn="v2",
            version=2,
            published_at=datetime.now(UTC) + timedelta(seconds=1),
        )
        await db_session.refresh(fam)
        assert fam.current_published_module_id == v2.id

        repo = ModuleRepository(db_session)
        await repo.retire_module(v2.id)

        await db_session.refresh(fam)
        # Pointer falls back to v1.
        assert fam.current_published_module_id == v1.id

    async def test_retire_clears_family_pointer_when_no_other_published(
        self, db_session: AsyncSession
    ) -> None:
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, title_bn="only")
        await db_session.refresh(fam)
        assert fam.current_published_module_id == v1.id

        repo = ModuleRepository(db_session)
        await repo.retire_module(v1.id)

        await db_session.refresh(fam)
        assert fam.current_published_module_id is None

    async def test_retiring_non_pointer_version_does_not_clear_pointer(
        self, db_session: AsyncSession
    ) -> None:
        """Retiring v1 when v2 is the family's current pointer must leave
        the pointer at v2."""
        fam = await _make_family(db_session)
        v1 = await _make_module(db_session, family=fam, title_bn="v1", version=1, set_family_pointer=False)
        v2 = await _make_module(db_session, family=fam, title_bn="v2", version=2)
        # Pointer is on v2.
        await db_session.refresh(fam)
        assert fam.current_published_module_id == v2.id

        repo = ModuleRepository(db_session)
        await repo.retire_module(v1.id)

        await db_session.refresh(fam)
        assert fam.current_published_module_id == v2.id

    async def test_retire_unknown_raises(self, db_session: AsyncSession) -> None:
        repo = ModuleRepository(db_session)
        with pytest.raises(ModuleNotFoundError):
            await repo.retire_module(uuid4())


# ─── count_modules: mirror of list-default ─────────────────────────────────


class TestCountModules:
    async def test_default_excludes_retired(self, db_session: AsyncSession) -> None:
        fam = await _make_family(db_session)
        await _make_module(db_session, family=fam, title_bn="live")
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            title_bn="retired",
            lifecycle_status="retired",
            set_family_pointer=False,
        )

        repo = ModuleRepository(db_session)
        # Count all (excludes retired by default). We can't pin an exact
        # number because other tests in the same session might have left
        # rows; instead assert that count(default) == count(status=published)
        # for the modules we just inserted (no other state should be retired).
        published = await repo.count_modules(status="published")
        default = await repo.count_modules()
        retired = await repo.count_modules(status="retired")
        assert default == published
        assert retired >= 1  # at least our retired one

    async def test_clinically_reviewed_filter_count(self, db_session: AsyncSession) -> None:
        # Use a unique tag in description so we can isolate.
        marker = f"count-test-{uuid4().hex[:6]}"
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            description_bn=marker,
            clinically_reviewed=True,
        )
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            description_bn=marker,
            clinically_reviewed=False,
        )
        await _make_module(
            db_session,
            family=await _make_family(db_session),
            description_bn=marker,
            clinically_reviewed=False,
        )

        # Count flips with the filter.
        repo = ModuleRepository(db_session)
        # Direct query for our marker since count_modules lacks a description filter.
        reviewed = (
            (
                await db_session.execute(
                    select(
                        ModuleRepository.__init__.__globals__["Module"]
                    ).where(  # use Module from the repo's namespace
                        Module.description_bn == marker, Module.clinically_reviewed.is_(True)
                    )
                )
            )
            .scalars()
            .all()
        )
        unreviewed = (
            (
                await db_session.execute(
                    select(Module).where(
                        Module.description_bn == marker, Module.clinically_reviewed.is_(False)
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(reviewed) == 1
        assert len(unreviewed) == 2
        # And the repo's count_modules with the flag filter is at least these.
        assert await repo.count_modules(clinically_reviewed=True) >= 1
        assert await repo.count_modules(clinically_reviewed=False) >= 2


# Suppress unused-import lint when only referenced via select(...)
_ = UUID
