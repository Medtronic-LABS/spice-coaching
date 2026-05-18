"""W-7 — pipeline orchestrator.

Drives one source_document through Stages A → B → C → D, persisting
ingestion_run + ingestion_run_step state at every transition. Designed to
be:

- **Resumable**: re-running on a partially-failed run skips stages whose
  step row is already 'succeeded'. LLM-bound stages (B/C/D) additionally
  hit `llm_call_cache` for cheap re-execution, so even when a step row is
  missing or failed, the underlying ai-runtime calls aren't repeated.
- **Concurrency-safe**: refuses to start a second run for the same
  source_document while one is already 'running'.
- **Failure-isolating**: a failing stage marks the run partially_succeeded
  rather than failed — downstream stages are skipped, but the run remains
  resumable. A run is marked `failed` only when Stage A (the entry point)
  blows up.

We deliberately don't pull in LangGraph: the pipeline is linear with no
real branching. Per-candidate Stage D parallelism is handled in-process
via sequential awaits (deterministic ordering for tests; pilot corpora
are small enough that parallelism doesn't matter yet).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.module_candidate_draft import ModuleCandidateDraft
from platform_service.db.repositories.module_candidate_repository import (
    ModuleCandidateRepository,
)
from platform_service.integrations.ai_runtime_client import AIRuntimeClient
from platform_service.services.card_drafter import CardDrafter
from platform_service.services.llm_call_cache_service import CachingAIRuntimeClient
from platform_service.services.module_identifier import ModuleIdentifier
from platform_service.services.run_state_service import (
    RUN_FAILED,
    RUN_PARTIALLY_SUCCEEDED,
    RUN_SUCCEEDED,
    STAGE_CARD_DRAFT,
    STAGE_EXTRACT,
    STAGE_MODULE_IDENTIFY,
    RunStateService,
)
from platform_service.workers.extractors.vision_extractor import VisionExtractor
from platform_service.workers.stage_a_extract import Stage1ExtractionError, StageAExtractor
from platform_service.workers.stage_c_identify import StageCOrchestrator
from platform_service.workers.stage_d_draft import StageDOrchestrator

logger = logging.getLogger(__name__)


@dataclass
class StageOutcome:
    """Per-stage execution summary (one entry in PipelineResult.stages)."""

    stage: str
    status: str  # succeeded | failed | skipped
    summary: dict | None = None
    error: dict | None = None


@dataclass
class PipelineResult:
    """End-to-end outcome of one orchestrator run."""

    run_id: UUID
    source_document_id: UUID
    final_status: str  # succeeded | failed | partially_succeeded
    stages: list[StageOutcome] = field(default_factory=list)
    candidates_emitted: int = 0
    drafts_produced: int = 0


class PipelineOrchestrator:
    """Single entry point for one-document pipeline execution."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        ai_client: AIRuntimeClient | CachingAIRuntimeClient | None = None,
        stage_a: StageAExtractor | None = None,
        stage_c: StageCOrchestrator | None = None,
        stage_d: StageDOrchestrator | None = None,
    ) -> None:
        self._session = session
        self._run_state = RunStateService(session)
        self._candidate_repo = ModuleCandidateRepository(session)

        # Caching wrapper: every LLM-bound stage we instantiate by default
        # gets the cache so resume-from-cache works without per-stage opt-in.
        # Tests can pass their own ai_client (or a fully-mocked stage)
        # to bypass.
        if ai_client is None:
            ai_client = CachingAIRuntimeClient(session=session)
        self._ai_client = ai_client

        # Stages — accept overrides for test injection. Outline assembly
        # was a separate Stage B; per the architecture reset it is folded
        # into Stage 1 (`StageAExtractor` writes outline_jsonb at the tail
        # of its run and fails the stage if the outline is empty).
        self._stage_a = stage_a or StageAExtractor(
            session,
            vision_extractor=VisionExtractor(client=ai_client),
        )
        self._stage_c = stage_c or StageCOrchestrator(
            session,
            identifier=ModuleIdentifier(client=ai_client),
        )
        self._stage_d = stage_d or StageDOrchestrator(
            session,
            card_drafter=CardDrafter(client=ai_client),
        )

    # ── Entry ───────────────────────────────────────────────────────────

    async def run(
        self,
        *,
        source_document_id: UUID,
        source_path: str | Path,
        source_type: str,
        primary_language: str = "bn",
        triggered_by: UUID | None = None,
        resume: bool = True,
    ) -> PipelineResult:
        """Execute the full A→B→C→D pipeline for one source document.

        If `resume=True` and a partially-failed run exists for this document,
        we attach to that run and skip already-succeeded stages.
        """
        run = None
        if resume:
            run = await self._run_state.find_resumable_run(source_document_id)
            if run is not None:
                logger.info(
                    "Resuming ingestion_run %s for source_document %s",
                    run.id,
                    source_document_id,
                )
        if run is None:
            run = await self._run_state.start_run(
                source_document_id=source_document_id,
                triggered_by=triggered_by,
            )
            await self._session.commit()  # surface the run to polling endpoints
        # Snapshot the run primary key. Recovery paths inside `_run_drafting`
        # rollback the session, expiring all attached ORM objects — accessing
        # `run.id` afterwards triggers an implicit DB reload outside greenlet
        # context (MissingGreenlet). Carry the UUID by value instead.
        run_id: UUID = run.id
        result = PipelineResult(
            run_id=run_id,
            source_document_id=source_document_id,
            final_status=RUN_SUCCEEDED,
        )

        # Stage A — extraction
        ok = await self._run_extract(
            result=result,
            run_id=run_id,
            source_document_id=source_document_id,
            source_path=source_path,
            source_type=source_type,
            primary_language=primary_language,
        )
        if not ok:
            # Stage A is the precondition for everything else; mark run failed
            # outright (not partially) — there's nothing to recover.
            await self._run_state.complete_run(
                run_id,
                status=RUN_FAILED,
                error_jsonb={"failed_stage": STAGE_EXTRACT},
            )
            await self._session.commit()
            result.final_status = RUN_FAILED
            return result

        # Stage 2 — module identification (outline was folded into Stage 1)
        ok, candidates_emitted = await self._run_identify(
            result=result,
            run_id=run_id,
            source_document_id=source_document_id,
        )
        if not ok:
            await self._run_state.complete_run(
                run_id,
                status=RUN_PARTIALLY_SUCCEEDED,
                error_jsonb={"failed_stage": STAGE_MODULE_IDENTIFY},
            )
            await self._session.commit()
            result.final_status = RUN_PARTIALLY_SUCCEEDED
            return result
        result.candidates_emitted = candidates_emitted

        # Stage D — per-candidate drafting
        if candidates_emitted == 0:
            await self._run_state.skip_step(
                run_id=run_id,
                stage=STAGE_CARD_DRAFT,
                reason="no_candidates_from_stage_c",
            )
            result.stages.append(
                StageOutcome(
                    stage=STAGE_CARD_DRAFT,
                    status="skipped",
                    summary={"reason": "no_candidates_from_stage_c"},
                )
            )
            await self._run_state.complete_run(run_id, status=RUN_SUCCEEDED)
            await self._session.commit()
            result.final_status = RUN_SUCCEEDED
            return result

        drafts_produced, draft_failures = await self._run_drafting(
            result=result,
            run_id=run_id,
        )
        result.drafts_produced = drafts_produced

        # Final run status: any draft failure → partially_succeeded, else succeeded.
        if draft_failures > 0:
            await self._run_state.complete_run(
                run_id,
                status=RUN_PARTIALLY_SUCCEEDED,
                error_jsonb={
                    "failed_stage": STAGE_CARD_DRAFT,
                    "draft_failures": draft_failures,
                    "drafts_produced": drafts_produced,
                },
            )
            result.final_status = RUN_PARTIALLY_SUCCEEDED
        else:
            await self._run_state.complete_run(run_id, status=RUN_SUCCEEDED)
            result.final_status = RUN_SUCCEEDED
        await self._session.commit()
        return result

    async def run_generator(
        self,
        *,
        source_document_id: UUID,
        source_path: str | Path,
        source_type: str,
        primary_language: str = "bn",
        triggered_by: UUID | None = None,
        resume: bool = True,
    ) -> AsyncGenerator[dict, None]:
        """Like run(), but yields SSE-style progress dicts at each stage transition.

        Each yielded dict has at minimum:
          {"event": <str>, "run_id": <str>, ...}

        Events emitted:
          run_started       — initial run row created
          stage_started     — a stage has begun
          stage_succeeded   — a stage completed successfully
          stage_skipped     — a stage was skipped (resume)
          stage_failed      — a stage failed
          pipeline_complete — final event with full PipelineResult summary
        """
        run = None
        if resume:
            run = await self._run_state.find_resumable_run(source_document_id)
        if run is None:
            run = await self._run_state.start_run(
                source_document_id=source_document_id,
                triggered_by=triggered_by,
            )
            await self._session.commit()

        run_id_str = str(run.id)
        result = PipelineResult(
            run_id=run.id,
            source_document_id=source_document_id,
            final_status=RUN_SUCCEEDED,
        )

        yield {"event": "run_started", "run_id": run_id_str, "source_document_id": str(source_document_id)}

        # Stage A
        yield {"event": "stage_started", "run_id": run_id_str, "stage": STAGE_EXTRACT}
        ok = await self._run_extract(
            result=result,
            run_id=run.id,
            source_document_id=source_document_id,
            source_path=source_path,
            source_type=source_type,
            primary_language=primary_language,
        )
        outcome_a = result.stages[-1]
        if outcome_a.status == "skipped":
            yield {"event": "stage_skipped", "run_id": run_id_str, "stage": STAGE_EXTRACT}
        elif ok:
            yield {
                "event": "stage_succeeded",
                "run_id": run_id_str,
                "stage": STAGE_EXTRACT,
                "summary": outcome_a.summary,
            }
        else:
            yield {
                "event": "stage_failed",
                "run_id": run_id_str,
                "stage": STAGE_EXTRACT,
                "error": outcome_a.error,
            }
            await self._run_state.complete_run(
                run.id, status=RUN_FAILED, error_jsonb={"failed_stage": STAGE_EXTRACT}
            )
            await self._session.commit()
            result.final_status = RUN_FAILED
            yield {"event": "pipeline_complete", "run_id": run_id_str, "final_status": result.final_status}
            return

        # Stage 2 — module identification (outline was folded into Stage 1)
        yield {"event": "stage_started", "run_id": run_id_str, "stage": STAGE_MODULE_IDENTIFY}
        ok, candidates_emitted = await self._run_identify(
            result=result,
            run_id=run.id,
            source_document_id=source_document_id,
        )
        outcome_c = result.stages[-1]
        if outcome_c.status == "skipped":
            yield {"event": "stage_skipped", "run_id": run_id_str, "stage": STAGE_MODULE_IDENTIFY}
        elif ok:
            result.candidates_emitted = candidates_emitted
            yield {
                "event": "stage_succeeded",
                "run_id": run_id_str,
                "stage": STAGE_MODULE_IDENTIFY,
                "summary": outcome_c.summary,
            }
        else:
            yield {
                "event": "stage_failed",
                "run_id": run_id_str,
                "stage": STAGE_MODULE_IDENTIFY,
                "error": outcome_c.error,
            }
            await self._run_state.complete_run(
                run.id, status=RUN_PARTIALLY_SUCCEEDED, error_jsonb={"failed_stage": STAGE_MODULE_IDENTIFY}
            )
            await self._session.commit()
            result.final_status = RUN_PARTIALLY_SUCCEEDED
            yield {"event": "pipeline_complete", "run_id": run_id_str, "final_status": result.final_status}
            return

        # Stage D
        yield {"event": "stage_started", "run_id": run_id_str, "stage": STAGE_CARD_DRAFT}
        if candidates_emitted == 0:
            await self._run_state.skip_step(
                run_id=run.id, stage=STAGE_CARD_DRAFT, reason="no_candidates_from_stage_c"
            )
            result.stages.append(
                StageOutcome(
                    stage=STAGE_CARD_DRAFT, status="skipped", summary={"reason": "no_candidates_from_stage_c"}
                )
            )
            await self._run_state.complete_run(run.id, status=RUN_SUCCEEDED)
            await self._session.commit()
            result.final_status = RUN_SUCCEEDED
            yield {
                "event": "stage_skipped",
                "run_id": run_id_str,
                "stage": STAGE_CARD_DRAFT,
                "reason": "no_candidates_from_stage_c",
            }
            yield {
                "event": "pipeline_complete",
                "run_id": run_id_str,
                "final_status": result.final_status,
                "candidates_emitted": 0,
                "drafts_produced": 0,
            }
            return

        drafts_produced, draft_failures = await self._run_drafting(result=result, run_id=run.id)
        result.drafts_produced = drafts_produced
        outcome_d = result.stages[-1]
        if outcome_d.status == "skipped":
            yield {"event": "stage_skipped", "run_id": run_id_str, "stage": STAGE_CARD_DRAFT}
        elif draft_failures > 0:
            yield {
                "event": "stage_failed",
                "run_id": run_id_str,
                "stage": STAGE_CARD_DRAFT,
                "error": outcome_d.error,
            }
            await self._run_state.complete_run(
                run.id,
                status=RUN_PARTIALLY_SUCCEEDED,
                error_jsonb={
                    "failed_stage": STAGE_CARD_DRAFT,
                    "draft_failures": draft_failures,
                    "drafts_produced": drafts_produced,
                },
            )
            result.final_status = RUN_PARTIALLY_SUCCEEDED
        else:
            yield {
                "event": "stage_succeeded",
                "run_id": run_id_str,
                "stage": STAGE_CARD_DRAFT,
                "summary": outcome_d.summary,
            }
            await self._run_state.complete_run(run.id, status=RUN_SUCCEEDED)
            result.final_status = RUN_SUCCEEDED
        await self._session.commit()

        yield {
            "event": "pipeline_complete",
            "run_id": run_id_str,
            "final_status": result.final_status,
            "candidates_emitted": result.candidates_emitted,
            "drafts_produced": result.drafts_produced,
        }

    # ── Stage runners ───────────────────────────────────────────────────

    async def _run_extract(
        self,
        *,
        result: PipelineResult,
        run_id: UUID,
        source_document_id: UUID,
        source_path: str | Path,
        source_type: str,
        primary_language: str,
    ) -> bool:
        if await self._run_state.is_stage_succeeded(run_id, stage=STAGE_EXTRACT):
            logger.info("Resume: skipping Stage A (already succeeded)")
            result.stages.append(StageOutcome(stage=STAGE_EXTRACT, status="skipped"))
            return True
        step = await self._run_state.start_step(
            run_id=run_id,
            stage=STAGE_EXTRACT,
            input_summary={
                "source_document_id": str(source_document_id),
                "source_type": source_type,
            },
        )
        # Capture PK before commit — expire_on_commit=True (default) would
        # otherwise force a lazy-load on step.id from inside the failure path,
        # which raises MissingGreenlet on async sessions.
        step_id = step.id
        await self._session.commit()  # mark stage as 'running' for observers
        try:
            stage_a_result = await self._stage_a.run(
                source_document_id=source_document_id,
                source_path=source_path,
                source_type=source_type,
                primary_language=primary_language,
            )
        except Stage1ExtractionError as exc:
            # Typed: outline_empty / no_pages / etc. Caller can branch on
            # error_jsonb.reason instead of parsing the message string.
            logger.error("Stage 1 contract violation for source_document %s: %s", source_document_id, exc)
            await self._session.rollback()
            error = {
                "type": "Stage1ExtractionError",
                "reason": "outline_empty",
                "message": str(exc)[:500],
            }
            await self._run_state.fail_step(step_id, error=error)
            await self._session.commit()
            result.stages.append(StageOutcome(stage=STAGE_EXTRACT, status="failed", error=error))
            return False
        except Exception as exc:
            logger.exception("Stage 1 crashed for source_document %s", source_document_id)
            await self._session.rollback()
            await self._run_state.fail_step(
                step_id, error={"type": type(exc).__name__, "message": str(exc)[:500]}
            )
            await self._session.commit()
            result.stages.append(
                StageOutcome(
                    stage=STAGE_EXTRACT,
                    status="failed",
                    error={"type": type(exc).__name__, "message": str(exc)[:500]},
                )
            )
            return False
        summary = {
            "total_pages": stage_a_result.total_pages,
            "pages_persisted": stage_a_result.pages_persisted,
            "extraction_method_counts": stage_a_result.extraction_method_counts,
            # Outline assembly is now part of Stage 1; surface the section
            # count in the step summary so an empty-outline failure (caught
            # by Stage1ExtractionError above) is observable in run history.
            "outline_section_count": stage_a_result.outline_section_count,
        }
        await self._run_state.complete_step(step_id, output_summary=summary)
        await self._session.commit()  # persist Stage 1 output before Stage 2 starts
        result.stages.append(StageOutcome(stage=STAGE_EXTRACT, status="succeeded", summary=summary))
        return True

    async def _run_identify(
        self,
        *,
        result: PipelineResult,
        run_id: UUID,
        source_document_id: UUID,
    ) -> tuple[bool, int]:
        if await self._run_state.is_stage_succeeded(run_id, stage=STAGE_MODULE_IDENTIFY):
            logger.info("Resume: skipping Stage C (already succeeded)")
            existing = await self._candidate_repo.list_candidates_for_run(run_id)
            result.stages.append(
                StageOutcome(
                    stage=STAGE_MODULE_IDENTIFY,
                    status="skipped",
                    summary={"existing_candidates": len(existing)},
                )
            )
            return True, len(existing)
        step = await self._run_state.start_step(
            run_id=run_id,
            stage=STAGE_MODULE_IDENTIFY,
            input_summary={"source_document_ids": [str(source_document_id)]},
        )
        step_id = step.id  # capture before commit (see Stage A comment)
        await self._session.commit()  # mark stage as 'running' for observers
        try:
            stage_c_result = await self._stage_c.run(
                ingestion_run_id=run_id,
                source_document_ids=[source_document_id],
            )
        except Exception as exc:
            logger.exception("Stage C failed for run %s", run_id)
            await self._session.rollback()
            await self._run_state.fail_step(
                step_id, error={"type": type(exc).__name__, "message": str(exc)[:500]}
            )
            await self._session.commit()
            result.stages.append(
                StageOutcome(
                    stage=STAGE_MODULE_IDENTIFY,
                    status="failed",
                    error={"type": type(exc).__name__, "message": str(exc)[:500]},
                )
            )
            return False, 0
        summary = {
            "candidates_emitted": stage_c_result.candidates_emitted,
            "candidates_flagged": stage_c_result.candidates_flagged,
            "flag_counts": stage_c_result.flag_counts,
            "chunks_attempted": stage_c_result.chunks_attempted,
            "chunks_succeeded": stage_c_result.chunks_succeeded,
            "chunks_failed": stage_c_result.chunks_failed,
            "cross_chunk_review_count": stage_c_result.cross_chunk_review_count,
        }
        await self._run_state.complete_step(step_id, output_summary=summary)
        await self._session.commit()  # persist candidates before D starts
        result.stages.append(StageOutcome(stage=STAGE_MODULE_IDENTIFY, status="succeeded", summary=summary))
        return True, stage_c_result.candidates_emitted

    async def _run_drafting(
        self,
        *,
        result: PipelineResult,
        run_id: UUID,
    ) -> tuple[int, int]:
        """Run Stage D for each candidate. Returns (drafts_produced, failures)."""
        candidates: list[ModuleCandidateDraft] = await self._candidate_repo.list_candidates_for_run(run_id)
        # Snapshot primary keys before the loop. A rollback inside the
        # per-candidate failure path expires *every* attached ORM object,
        # so accessing `cand.id` on later iterations would trigger an
        # implicit DB reload outside greenlet context (MissingGreenlet).
        candidate_ids: list[UUID] = [cand.id for cand in candidates]
        drafts_produced = 0
        failures = 0
        for cand_id in candidate_ids:
            input_match = {"candidate_id": str(cand_id)}
            if await self._run_state.is_stage_succeeded(
                run_id, stage=STAGE_CARD_DRAFT, input_match=input_match
            ):
                drafts_produced += 1
                continue
            step = await self._run_state.start_step(
                run_id=run_id,
                stage=STAGE_CARD_DRAFT,
                input_summary=input_match,
            )
            step_id = step.id  # capture before commit (see Stage A comment)
            await self._session.commit()  # mark stage as 'running' for observers
            try:
                stage_d_result = await self._stage_d.run(candidate_id=cand_id)
            except Exception as exc:
                logger.exception("Stage D failed for candidate %s", cand_id)
                # Roll back any partial Stage D state for this candidate
                # (otherwise SQLAlchemy stays in a poisoned txn) and record
                # the failure on a fresh transaction.
                await self._session.rollback()
                await self._run_state.fail_step(
                    step_id,
                    error={"type": type(exc).__name__, "message": str(exc)[:500]},
                )
                await self._session.commit()
                result.stages.append(
                    StageOutcome(
                        stage=STAGE_CARD_DRAFT,
                        status="failed",
                        error={
                            "candidate_id": str(cand_id),
                            "type": type(exc).__name__,
                            "message": str(exc)[:500],
                        },
                    )
                )
                failures += 1
                continue
            summary = {
                "candidate_id": str(cand_id),
                "module_id": str(stage_d_result.module_id) if stage_d_result.module_id else None,
                "cards_count": stage_d_result.cards_count,
                "questions_count": stage_d_result.questions_count,
                "insufficient_reason": stage_d_result.insufficient_reason,
            }
            await self._run_state.complete_step(step_id, output_summary=summary)
            await self._session.commit()  # persist this candidate's draft module
            result.stages.append(StageOutcome(stage=STAGE_CARD_DRAFT, status="succeeded", summary=summary))
            if stage_d_result.module_id is not None:
                drafts_produced += 1
        return drafts_produced, failures
