"""Stage 2b orchestrator — load candidates, fuse, draft, publish, retire.

This module wraps the pure-compute `CrossSourceFuser` with the DB-side
glue needed to make fusion an end-to-end operation:

1. Load every candidate from the latest non-fusion ingestion run for
   each source_document_id in the request.
2. Call `CrossSourceFuser.fuse(candidates)` to identify cross-source
   pairings (e.g., BRAC clinical "ANC counselling" + UHIS workflow
   "Conducting ANC visits" → one fused unit).
3. Persist each fusion group as a new `module_candidate_draft` row
   anchored on a freshly-created "fusion" `ingestion_run`. The fused
   row's `source_provenance` is the union of constituents'; its
   `quality_flags_jsonb` carries `merge_lineage` for audit.
4. Draft each fused candidate via the existing `StageDOrchestrator`,
   producing modules whose `source_document_ids` array spans the
   constituents' source docs and whose cards cite blocks from each
   source (drafter v2's cross-source coverage rule, see
   card_drafter_prompt.py).
5. Retire constituent modules: for every constituent candidate id,
   find the published module whose `title_en` matches the candidate's
   `proposed_title` AND whose `source_document_ids` overlaps the
   candidate's source — set `lifecycle_status = 'retired'`. The
   Android client filters on `published`, so retired constituents
   stop surfacing without a schema migration. Heuristic match (no
   candidate→module FK exists today); good enough for the BRAC+UHIS
   pilot and trivially upgradable to an FK column later.

The unfused candidates (most of the input — single-source candidates
with no cross-source counterpart) are left untouched. Their
already-published per-source modules continue to ship. Only the
constituents of actual fusion groups get retired.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.ingestion_run import IngestionRun
from platform_service.db.repositories.module_candidate_repository import (
    ModuleCandidateRepository,
)
from platform_service.services.cross_source_fuser import CrossSourceFuser, FusionGroup
from platform_service.workers.stage_d_draft import StageDOrchestrator

logger = logging.getLogger(__name__)


@dataclass
class FusionRunSummary:
    """Per-fusion-call audit record. Returned to the API caller for
    immediate visibility; the same data is observable later via the
    fusion ingestion_run row + persisted candidates' merge_lineage."""

    fusion_run_id: UUID
    input_candidate_count: int
    fusion_group_count: int
    fused_modules_published: int
    fused_modules_failed: int
    fused_modules_with_coverage_warning: int
    constituents_retired: int
    drafts: list[dict[str, Any]] = field(default_factory=list)


class CrossSourceFusionRunner:
    """Orchestrates the full Stage 2b → Stage 3 → publish flow for a
    multi-source workspace."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        fuser: CrossSourceFuser | None = None,
        stage_d: StageDOrchestrator | None = None,
    ) -> None:
        self._session = session
        self._fuser = fuser or CrossSourceFuser()
        self._stage_d = stage_d or StageDOrchestrator(session)

    async def run(self, source_document_ids: list[UUID]) -> FusionRunSummary:
        if len(source_document_ids) < 2:
            raise ValueError(
                f"cross-source fusion requires ≥2 source_document_ids; got {len(source_document_ids)}"
            )

        candidates = await self._load_candidates(source_document_ids)
        if not candidates:
            raise ValueError(
                f"no candidates found for source_document_ids={source_document_ids}; "
                "ensure each doc has a completed Stage 2a ingestion run"
            )
        candidates_by_id: dict[str, dict[str, Any]] = {c["id"]: c for c in candidates}
        logger.info(
            "Stage 2b runner: loaded %d candidates across %d source documents",
            len(candidates),
            len(source_document_ids),
        )

        # Fusion call (pure compute, mocked in tests)
        fusion_result = await self._fuser.fuse(candidates)
        if not fusion_result.fusion_groups:
            logger.info("Stage 2b runner: no fusion groups emerged — nothing to draft")
            return FusionRunSummary(
                fusion_run_id=uuid.uuid4(),  # not persisted; caller can ignore
                input_candidate_count=len(candidates),
                fusion_group_count=0,
                fused_modules_published=0,
                fused_modules_failed=0,
                fused_modules_with_coverage_warning=0,
                constituents_retired=0,
            )

        fusion_run_id = await self._create_fusion_run(source_document_ids[0])
        await self._session.commit()
        logger.info(
            "Stage 2b runner: created fusion ingestion_run %s; persisting %d fused candidates",
            fusion_run_id,
            len(fusion_result.fusion_groups),
        )

        fused_candidate_ids: list[tuple[UUID, FusionGroup, set[str]]] = []
        for group in fusion_result.fusion_groups:
            cid = await self._persist_fused_candidate(fusion_run_id, group, candidates_by_id)
            # Compute the expected source set for this group so the
            # drafter validation knows which sources MUST appear in
            # the resulting module's card-level citations.
            expected_sources = {
                str(candidates_by_id[str(c)]["source_document_id"]) for c in group.constituent_ids
            }
            fused_candidate_ids.append((cid, group, expected_sources))
        await self._session.commit()

        # Draft each fused candidate via Stage 3. Two layers of retry:
        #   - inner: JSON-truncation retry inside _draft_with_retry
        #     (Vertex occasionally returns truncated JSON).
        #   - outer: cross-source coverage retry. The drafter LLM is
        #     stochastic — on ~25% of samples it ignores the v2 rule
        #     and produces single-source cards despite balanced input.
        #     Validate the resulting module's card-level citations
        #     against expected_sources; one retry if missing any.
        published = 0
        failed = 0
        coverage_warnings = 0
        drafts: list[dict[str, Any]] = []
        for fc_id, group, expected_sources in fused_candidate_ids:
            module_id, cards_count, reason, coverage_ok = await self._draft_with_coverage(
                fc_id, expected_sources
            )
            drafts.append(
                {
                    "fused_candidate_id": str(fc_id),
                    "module_id": str(module_id) if module_id else None,
                    "cards_count": cards_count,
                    "merged_title": group.merged_title,
                    "constituent_candidate_ids": [str(cid) for cid in group.constituent_ids],
                    "insufficient_reason": reason,
                    "cross_source_coverage_ok": coverage_ok,
                }
            )
            if module_id is not None:
                published += 1
                if not coverage_ok:
                    coverage_warnings += 1
            else:
                failed += 1

        # Retire the constituent modules whose candidates were absorbed
        # into fused modules. Constituents with no published module
        # (some never made it through Stage 3 originally) are silently
        # skipped — there's nothing to retire.
        all_constituent_ids: list[UUID] = []
        for _, group, _ in fused_candidate_ids:
            all_constituent_ids.extend(group.constituent_ids)
        retired = await self._retire_constituent_modules(all_constituent_ids, candidates_by_id)

        await self._session.execute(
            text("UPDATE ingestion_run SET status='succeeded', completed_at=now() WHERE id=:rid"),
            {"rid": str(fusion_run_id)},
        )
        await self._session.commit()

        logger.info(
            "Stage 2b runner: fusion_run=%s published=%d failed=%d coverage_warnings=%d retired_constituents=%d",
            fusion_run_id,
            published,
            failed,
            coverage_warnings,
            retired,
        )
        return FusionRunSummary(
            fusion_run_id=fusion_run_id,
            input_candidate_count=len(candidates),
            fusion_group_count=len(fusion_result.fusion_groups),
            fused_modules_published=published,
            fused_modules_failed=failed,
            fused_modules_with_coverage_warning=coverage_warnings,
            constituents_retired=retired,
            drafts=drafts,
        )

    # ── internals ─────────────────────────────────────────────────────

    async def _load_candidates(self, doc_ids: list[UUID]) -> list[dict[str, Any]]:
        """For each source_document_id, find its latest ingestion run
        whose status is in (succeeded, partially_succeeded) AND whose
        error_jsonb does NOT mark it as a cross_source_fusion run
        (those are fusion outputs, not source candidates). Pull every
        candidate from those runs."""
        rows = (
            (
                await self._session.execute(
                    text("""
                    WITH latest_run AS (
                        SELECT DISTINCT ON (source_document_id)
                               id, source_document_id
                        FROM ingestion_run
                        WHERE source_document_id = ANY(:doc_ids)
                          AND status IN ('succeeded', 'partially_succeeded')
                          AND COALESCE(error_jsonb->>'type', '') != 'cross_source_fusion'
                        ORDER BY source_document_id, started_at DESC
                    )
                    SELECT d.id::text                       AS id,
                           lr.source_document_id::text      AS source_document_id,
                           d.proposed_title                 AS proposed_title,
                           d.scope_summary                  AS scope_summary,
                           d.proposed_module_type           AS proposed_module_type,
                           d.estimated_card_count           AS estimated_card_count,
                           d.estimated_quiz_count           AS estimated_quiz_count,
                           d.source_provenance_jsonb        AS source_provenance,
                           d.quality_flags_jsonb            AS quality_flags
                    FROM module_candidate_draft d
                    JOIN latest_run lr ON lr.id = d.ingestion_run_id
                    ORDER BY lr.source_document_id, d.created_at
                """),
                    {"doc_ids": [str(d) for d in doc_ids]},
                )
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    async def _create_fusion_run(self, primary_doc_id: UUID) -> UUID:
        """Create an ingestion_run row anchored on the first source doc.
        Tagged via error_jsonb so future fusion runs can filter it out
        when loading source candidates (see _load_candidates)."""
        run = IngestionRun(
            id=uuid.uuid4(),
            source_document_id=primary_doc_id,
            status="running",
            error_jsonb={"type": "cross_source_fusion"},
        )
        self._session.add(run)
        await self._session.flush()
        return run.id

    async def _persist_fused_candidate(
        self,
        fusion_run_id: UUID,
        group: FusionGroup,
        candidates_by_id: dict[str, dict[str, Any]],
    ) -> UUID:
        """Insert one module_candidate_draft row representing the fused
        unit. source_provenance is the union of constituents'."""
        merged_prov: list[dict[str, Any]] = []
        constituent_titles: list[str] = []
        for cid in group.constituent_ids:
            c = candidates_by_id[str(cid)]
            constituent_titles.append(c["proposed_title"])
            for entry in c.get("source_provenance") or []:
                merged_prov.append(entry)

        # Module type: most fusions are clinical-manual + workflow-guide
        # (both initial_training). When constituents disagree the first
        # one wins — non-load-bearing, the drafter is type-aware anyway.
        module_type = candidates_by_id[str(group.constituent_ids[0])].get(
            "proposed_module_type", "initial_training"
        )

        quality_flags = {
            "flags": ["cross_source_fused"],
            "merge_lineage": {
                "constituent_candidate_ids": [str(cid) for cid in group.constituent_ids],
                "constituent_titles": constituent_titles,
                "pairing_rationale": group.pairing_rationale,
            },
        }

        repo = ModuleCandidateRepository(self._session)
        cand = await repo.create_candidate(
            ingestion_run_id=fusion_run_id,
            proposed_title=group.merged_title,
            scope_summary=group.merged_scope_summary,
            source_provenance=merged_prov,
            estimated_card_count=5,
            estimated_quiz_count=5,
            proposed_module_type=module_type,
            quality_flags=quality_flags,
        )
        return cand.id

    def _enqueue_post_publish(self, module_id: UUID) -> None:
        """Fire post-publish Celery tasks (quiz + embedding) for a module
        that the runner has decided to keep. Delegates to StageDOrchestrator's
        helper so we don't duplicate Celery task imports."""
        self._stage_d._enqueue_post_publish(module_id)

    async def _draft_with_coverage(
        self,
        candidate_id: UUID,
        expected_sources: set[str],
    ) -> tuple[UUID | None, int, str | None, bool]:
        """Draft + verify cross-source coverage. Up to 2 attempts.

        After each successful draft, query the new module's card-level
        block citations and check that every `expected_source` appears.
        On failure: delete the just-drafted module and retry once. If
        the second attempt also fails coverage, accept the result and
        return coverage_ok=False so the caller can flag for reviewer.

        Why this exists: the drafter's v2 cross-source rule is followed
        ~75% of the time on balanced multi-source input. The other ~25%
        regress to single-source cards. The pre-prompt-tweak diagnostic
        re-ran the same PNC fused candidate 3× with cache busted: all 3
        spanned both sources, vs the original (1 of 4) only-BRAC. Pure
        stochasticity, not a prompt bug.
        """
        last_module_id: UUID | None = None
        last_cards = 0
        last_reason: str | None = None
        for attempt in (1, 2):
            module_id, cards, reason = await self._draft_with_retry(candidate_id)
            if module_id is None:
                # Both inner attempts of _draft_with_retry already failed;
                # don't re-attempt the outer loop (the failure is hard,
                # not coverage-related).
                return None, 0, reason, False
            last_module_id, last_cards, last_reason = module_id, cards, reason
            actual_sources = await self._cards_source_set(module_id)
            missing = expected_sources - actual_sources
            if not missing:
                # Coverage passed — NOW enqueue post-publish jobs (quiz +
                # embedding). Skipped on the inner draft step to avoid the
                # FK race where a deleted-on-coverage-failure module's
                # quiz task tries to insert and fails.
                self._enqueue_post_publish(module_id)
                return module_id, cards, reason, True
            logger.warning(
                "Stage 2b: fused module %s attempt %d cards span %d/%d expected sources; %s",
                module_id,
                attempt,
                len(actual_sources & expected_sources),
                len(expected_sources),
                "retrying" if attempt < 2 else "accepting (best-effort), flagged for reviewer",
            )
            if attempt < 2:
                # Drop the partial module so the retry produces a fresh
                # one. We didn't enqueue post-publish jobs for it (Stage D
                # was called with enqueue_post_publish=False), so DELETE
                # is safe — no orphaned quiz/embedding tasks reference
                # this module_id.
                await self._session.execute(
                    text("DELETE FROM module WHERE id=:mid"),
                    {"mid": str(module_id)},
                )
                await self._session.commit()
                last_module_id = None
        # Fell through both attempts; coverage warning. Still enqueue
        # post-publish for the (best-effort) kept module so the reviewer
        # can see quiz output even on the imperfect fusion.
        if last_module_id is not None:
            self._enqueue_post_publish(last_module_id)
        return last_module_id, last_cards, last_reason, False

    async def _cards_source_set(self, module_id: UUID) -> set[str]:
        """Return the set of source_document_ids actually cited by the
        module's cards (joined through content_block → source_page)."""
        rows = await self._session.execute(
            text("""
                WITH cards AS (
                    SELECT (jsonb_array_elements(module_json->'cards'))->'source_block_ids' AS block_ids
                    FROM module
                    WHERE id = :mid
                )
                SELECT DISTINCT sp.source_document_id::text
                FROM cards
                CROSS JOIN LATERAL jsonb_array_elements_text(cards.block_ids) AS bid
                JOIN content_block bk ON bk.id = bid::uuid
                JOIN source_page sp ON sp.id = bk.source_page_id
            """),
            {"mid": str(module_id)},
        )
        return {row[0] for row in rows.all()}

    async def _draft_with_retry(self, candidate_id: UUID) -> tuple[UUID | None, int, str | None]:
        """Run StageDOrchestrator with one retry on transient errors
        (Vertex occasionally truncates JSON output mid-string). Returns
        (module_id, cards_count, insufficient_reason). On hard failure
        returns (None, 0, exception_class_name).

        IMPORTANT: commit IMMEDIATELY on success. Without this, a later
        retry's rollback would wipe the just-drafted module — observed
        on the BRAC+UHIS run where drafter attempt 1 on candidate B
        rolled back, also discarding candidate A's successful draft
        that hadn't been committed yet. End state: runner reported
        `published=N` but only `N-k` modules in DB.
        """
        last_exc: Exception | None = None
        for attempt in (1, 2):
            try:
                # enqueue_post_publish=False because the runner re-validates
                # coverage and may DELETE this module; we enqueue post-publish
                # tasks ourselves only after coverage succeeds.
                d_result = await self._stage_d.run(candidate_id=candidate_id, enqueue_post_publish=False)
                await self._session.commit()
                return d_result.module_id, d_result.cards_count, d_result.insufficient_reason
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Stage 3 drafter attempt %d failed for fused candidate %s: %s",
                    attempt,
                    candidate_id,
                    type(exc).__name__,
                )
                await self._session.rollback()
        return None, 0, type(last_exc).__name__ if last_exc else "Unknown"

    async def _retire_constituent_modules(
        self,
        constituent_ids: list[UUID],
        candidates_by_id: dict[str, dict[str, Any]],
    ) -> int:
        """Find published modules whose source candidate was a constituent
        of a fusion group; mark them retired.

        Heuristic match: title_en == candidate.proposed_title AND
        candidate's source_document_id is in module.source_document_ids
        AND lifecycle_status = 'published'. No candidate→module FK exists
        in the schema today (modules know their source DOCS, not their
        source CANDIDATE); the heuristic is precise enough because every
        per-source candidate produces exactly one module with title_en
        == proposed_title (the drafter's persistence path uses the
        candidate's English title verbatim).
        """
        if not constituent_ids:
            return 0
        retired = 0
        for cid in constituent_ids:
            c = candidates_by_id.get(str(cid))
            if c is None:
                continue
            title = c.get("proposed_title", "")
            sd_id = c.get("source_document_id")
            if not title or not sd_id:
                continue
            result = await self._session.execute(
                text("""
                    UPDATE module
                    SET lifecycle_status = 'retired'
                    WHERE lifecycle_status = 'published'
                      AND title_en = :title
                      AND :sd_id = ANY(source_document_ids)
                    RETURNING id
                """),
                {"title": title, "sd_id": str(sd_id)},
            )
            n = len(list(result.scalars().all()))
            if n:
                logger.info(
                    "Stage 2b runner: retired %d constituent module(s) titled %r (source %s)",
                    n,
                    title,
                    sd_id[:8] if sd_id else "?",
                )
            retired += n
        return retired
