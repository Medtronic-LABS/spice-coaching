"""Module repository — admin dashboard reads + edits.

Per `docs/ARCHITECTURE_RESET.md`. The W-6 reviewer-queue surface was
deleted; this repository serves the dashboard endpoints in
`api/admin_modules.py`. Cards are stored inline on `module.module_json`,
so reads compose the runtime payload from one row + a JOIN to
`module_quiz_question`. There are no per-card row queries.

Method conventions:
- Reads return Pydantic-friendly dicts so the FastAPI handlers can return
  them directly without a separate response-model conversion step.
- Writes flush only — the calling endpoint decides commit boundaries.
- Versioning: edits create a new `module` row in the same family with
  `version = current_version + 1`. The previous row stays as
  `lifecycle_status='published'` until the new one writes its own
  `published_at`; `module_family.current_published_module_id` always points
  at the latest version.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.module import Module
from platform_service.db.models.module_family import ModuleFamily
from platform_service.db.models.module_quiz_question import ModuleQuizQuestion


class ModuleNotFoundError(Exception):
    """Raised when a requested module does not exist (or has been retired
    and the caller asked to exclude retired)."""

    def __init__(self, module_id: UUID) -> None:
        super().__init__(f"module {module_id} not found")
        self.module_id = module_id


class ModuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Reads ───────────────────────────────────────────────────────────

    async def list_modules(
        self,
        *,
        status: str | None = None,
        clinically_reviewed: bool | None = None,
        has_visibility_window: bool | None = None,
        has_quality_flags: bool | None = None,
        domain: str | None = None,
        full_text_query: str | None = None,
        latest_version_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Module]:
        """Filterable module list. Default excludes retired modules (callers
        wanting them must pass status='retired' explicitly).

        full_text_query runs against title_bn / title_en / description_bn —
        Postgres ILIKE for now, tsvector index can be added later if
        needed.

        latest_version_only collapses each family to its highest-version
        row that matches the filters. Useful for the reviewer dashboard
        listing where multiple versions of the same family would clutter
        the view (e.g. v1 deprecated + v2 published showing as two rows).
        """
        stmt = select(Module)
        if status is not None:
            stmt = stmt.where(Module.lifecycle_status == status)
        else:
            stmt = stmt.where(Module.lifecycle_status != "retired")
        if clinically_reviewed is not None:
            stmt = stmt.where(Module.clinically_reviewed == clinically_reviewed)
        if has_visibility_window is True:
            stmt = stmt.where(Module.visibility_window.isnot(None))
        elif has_visibility_window is False:
            stmt = stmt.where(Module.visibility_window.is_(None))
        if has_quality_flags is True:
            # `quality_flags_jsonb IS NOT NULL AND != '{}'` — empty-dict
            # rows are functionally "no flags" and should not match.
            stmt = stmt.where(
                Module.quality_flags_jsonb.isnot(None),
                Module.quality_flags_jsonb != cast({}, JSONB),
            )
        elif has_quality_flags is False:
            stmt = stmt.where(
                or_(
                    Module.quality_flags_jsonb.is_(None),
                    Module.quality_flags_jsonb == cast({}, JSONB),
                )
            )
        if domain:
            stmt = stmt.where(Module.domain == domain)
        if full_text_query:
            pattern = f"%{full_text_query}%"
            stmt = stmt.where(
                or_(
                    Module.title_bn.ilike(pattern),
                    Module.title_en.ilike(pattern),
                    Module.description_bn.ilike(pattern),
                )
            )
        if latest_version_only:
            # Keep only the highest-version row per family, after filters.
            # Window-function subquery so the outer ORDER BY + LIMIT/OFFSET
            # continue to work normally.
            rank_sq = select(
                Module.id,
                func.row_number()
                .over(
                    partition_by=Module.module_family_id,
                    order_by=Module.version.desc(),
                )
                .label("rn"),
            ).subquery()
            stmt = stmt.join(rank_sq, Module.id == rank_sq.c.id).where(rank_sq.c.rn == 1)
        stmt = (
            stmt.order_by(Module.published_at.desc().nullslast(), Module.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_module(self, module_id: UUID) -> Module | None:
        return await self._session.get(Module, module_id)

    async def list_quiz_questions(self, module_id: UUID) -> list[ModuleQuizQuestion]:
        result = await self._session.execute(
            select(ModuleQuizQuestion)
            .where(ModuleQuizQuestion.module_id == module_id)
            .order_by(ModuleQuizQuestion.question_order.asc().nullslast())
        )
        return list(result.scalars().all())

    async def search_by_embedding(
        self,
        *,
        query_vector: list[float],
        limit: int = 10,
    ) -> list[tuple[Module, float]]:
        """Cosine-similarity search over `module.embedding`. Returns the
        top-k modules and their distance scores (lower = closer). Skips
        modules without an embedding (post-publish worker not run yet).
        """
        # `Module.embedding.cosine_distance(...)` is the pgvector adapter's
        # ORM-friendly accessor; emits `embedding <=> :vec` SQL with proper
        # vector-typed bind. Avoids the raw-SQL string-literal cast trick.
        distance = Module.embedding.cosine_distance(list(query_vector)).label("distance")
        stmt = (
            select(Module, distance)
            .where(Module.embedding.is_not(None), Module.lifecycle_status == "published")
            .order_by(distance.asc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [(mod, float(dist)) for mod, dist in rows]

    async def list_published_modules_for_primary_gap_ids(
        self,
        *,
        gap_ids: list[UUID],
        tenant_id: UUID,
    ) -> list[Module]:
        """Published modules whose `primary_gap_id` is in `gap_ids`, scoped to
        tenant-global (`tenant_id IS NULL`) or the given tenant."""
        if not gap_ids:
            return []
        tenant_filter = or_(Module.tenant_id.is_(None), Module.tenant_id == tenant_id)
        stmt = select(Module).where(
            Module.lifecycle_status == "published",
            Module.primary_gap_id.in_(gap_ids),
            tenant_filter,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_recent_published_one_per_family(
        self,
        *,
        tenant_id: UUID,
        limit: int = 5,
    ) -> list[Module]:
        """One published row per `module_family_id` (latest `created_at` in
        family), ordered by `created_at` descending, limited — for gap-suggestion
        fallback."""
        tenant_filter = or_(Module.tenant_id.is_(None), Module.tenant_id == tenant_id)
        rank_sq = (
            select(
                Module.id,
                func.row_number()
                .over(
                    partition_by=Module.module_family_id,
                    order_by=Module.created_at.desc(),
                )
                .label("rn"),
            )
            .where(Module.lifecycle_status == "published", tenant_filter)
            .subquery()
        )
        stmt = (
            select(Module)
            .join(rank_sq, Module.id == rank_sq.c.id)
            .where(rank_sq.c.rn == 1)
            .order_by(Module.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ── Writes ──────────────────────────────────────────────────────────

    async def edit_module(
        self,
        module_id: UUID,
        *,
        title_bn: str | None = None,
        title_en: str | None = None,
        description_bn: str | None = None,
        module_json: dict[str, Any] | None = None,
        visibility_window: Any | None = None,
        editor_id: UUID | None = None,
    ) -> Module:
        """Create a new version of the module with the supplied edits.

        We never mutate a published row in place — every edit produces a
        new `module` row with `version = previous + 1`, copying forward
        any fields the caller did not touch. The previous row is then
        marked `lifecycle_status='retired'` (with `deprecated_at`) so the
        dashboard's default `?status` filter (which hides retired) shows
        only the new version. Without this retire step every edit would
        double the row count for the family on the dashboard. The family
        pointer is updated to the new row.

        Callers that just want to flip `clinically_reviewed` should use
        `set_clinically_reviewed` instead — that's a metadata flip, not a
        content change, and does not version-bump.
        """
        current = await self._session.get(Module, module_id)
        if current is None or current.lifecycle_status == "retired":
            raise ModuleNotFoundError(module_id)
        next_version = current.version + 1
        now = datetime.now(UTC)
        new_module = Module(
            module_family_id=current.module_family_id,
            version=next_version,
            title_bn=title_bn if title_bn is not None else current.title_bn,
            title_en=title_en if title_en is not None else current.title_en,
            description_bn=description_bn if description_bn is not None else current.description_bn,
            description_en=current.description_en,
            domain=current.domain,
            sub_domain=current.sub_domain,
            module_type=current.module_type,
            tenant_id=current.tenant_id,
            primary_gap_id=current.primary_gap_id,
            estimated_minutes=current.estimated_minutes,
            difficulty_level=current.difficulty_level,
            source_document_ids=list(current.source_document_ids or []),
            urgent_publish=current.urgent_publish,
            module_json=copy.deepcopy(module_json)
            if module_json is not None
            else copy.deepcopy(current.module_json),
            visibility_window=visibility_window
            if visibility_window is not None
            else current.visibility_window,
            pass_threshold_override=current.pass_threshold_override,
            # Edit resets the clinical_reviewed flag — clinician must
            # re-confirm against the new content.
            clinically_reviewed=False,
            lifecycle_status="published",
            published_at=now,
            supersedes_module_id=current.id,
        )
        self._session.add(new_module)
        await self._session.flush()

        # Retire the previous published version so it falls out of the
        # default dashboard list (which excludes retired). Without this,
        # `?status=published` returns N rows for a family edited N times.
        current.lifecycle_status = "retired"
        current.deprecated_at = now

        family = await self._session.get(ModuleFamily, current.module_family_id)
        if family is not None:
            family.current_published_module_id = new_module.id
        await self._session.flush()
        return new_module

    async def set_clinically_reviewed(
        self,
        module_id: UUID,
        *,
        flag: bool,
        reviewer_id: UUID | None = None,
    ) -> Module:
        """Flip `clinically_reviewed` without version-bumping. Records the
        reviewer + timestamp."""
        module = await self._session.get(Module, module_id)
        if module is None or module.lifecycle_status == "retired":
            raise ModuleNotFoundError(module_id)
        module.clinically_reviewed = flag
        module.clinically_reviewed_at = datetime.now(UTC) if flag else None
        module.clinically_reviewed_by = reviewer_id if flag else None
        
        if flag:
            module.lifecycle_status = "published"
            module.published_at = datetime.now(UTC)
            
            # Update family pointer
            family = await self._session.get(ModuleFamily, module.module_family_id)
            if family is not None:
                family.current_published_module_id = module.id
                
        await self._session.flush()
        return module

    async def set_visibility_window(
        self,
        module_id: UUID,
        *,
        window: Any | None,
    ) -> Module:
        """Set or clear the visibility_window range. None clears."""
        module = await self._session.get(Module, module_id)
        if module is None or module.lifecycle_status == "retired":
            raise ModuleNotFoundError(module_id)
        module.visibility_window = window
        await self._session.flush()
        return module

    async def retire_module(self, module_id: UUID) -> Module:
        """Soft-delete: lifecycle_status → retired. Still readable via the
        list with status='retired' filter; no longer surfaced to runtime."""
        module = await self._session.get(Module, module_id)
        if module is None:
            raise ModuleNotFoundError(module_id)
        module.lifecycle_status = "retired"
        module.deprecated_at = datetime.now(UTC)
        # Also clear the family pointer so the dashboard's "current"
        # module-per-family lookup doesn't return a retired row.
        family = await self._session.get(ModuleFamily, module.module_family_id)
        if family is not None and family.current_published_module_id == module.id:
            # Find the next-most-recent published version (if any).
            stmt = (
                select(Module)
                .where(
                    Module.module_family_id == module.module_family_id,
                    Module.id != module.id,
                    Module.lifecycle_status == "published",
                )
                .order_by(Module.version.desc())
                .limit(1)
            )
            other = (await self._session.execute(stmt)).scalar_one_or_none()
            family.current_published_module_id = other.id if other else None
        await self._session.flush()
        return module

    # ── Aggregates / pagination helpers ─────────────────────────────────

    async def count_modules(
        self,
        *,
        status: str | None = None,
        clinically_reviewed: bool | None = None,
    ) -> int:
        stmt = select(func.count(Module.id))
        if status is not None:
            stmt = stmt.where(Module.lifecycle_status == status)
        else:
            stmt = stmt.where(Module.lifecycle_status != "retired")
        if clinically_reviewed is not None:
            stmt = stmt.where(Module.clinically_reviewed == clinically_reviewed)
        return int((await self._session.execute(stmt)).scalar_one())


__all__ = ["ModuleRepository", "ModuleNotFoundError"]
