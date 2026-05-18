"""W-7 — pipeline run state service.

Manages the ingestion_run + ingestion_run_step rows that track each pipeline
pass. The orchestrator (`workers/pipeline_orchestrator.py`) calls into this
service at every transition so that:
- Resume-after-failure can find the last completed step and skip ahead.
- Concurrent runs on the same source_document are rejected at start.
- Operators can query run/step status via admin or telemetry tooling.

The tables are staging-only (30-day retention per Pipeline §16 P3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.models.ingestion_run import IngestionRun, IngestionRunStep

# Canonical stage names used as ingestion_run_step.stage values.
# Outline assembly was its own stage in v3.3 (`outline`); per the
# architecture reset it is folded into Stage 1 (`extract`), so the canonical
# set is three stages, not four. Per-candidate Stage 2-draft rows carry
# input_summary={"candidate_id":...}.
STAGE_EXTRACT = "extract"
STAGE_MODULE_IDENTIFY = "module_identify"
STAGE_CARD_DRAFT = "card_draft"

ALL_STAGES = (STAGE_EXTRACT, STAGE_MODULE_IDENTIFY, STAGE_CARD_DRAFT)

# Run statuses
RUN_RUNNING = "running"
RUN_SUCCEEDED = "succeeded"
RUN_FAILED = "failed"
RUN_PARTIALLY_SUCCEEDED = "partially_succeeded"

# Step statuses
STEP_PENDING = "pending"
STEP_RUNNING = "running"
STEP_SUCCEEDED = "succeeded"
STEP_FAILED = "failed"
STEP_SKIPPED = "skipped"


class ConcurrentRunError(Exception):
    """Raised when starting a new run while another is already running for
    the same source_document_id."""

    def __init__(self, source_document_id: UUID, existing_run_id: UUID) -> None:
        super().__init__(
            f"source_document {source_document_id} already has an active run "
            f"({existing_run_id}); refuse to start a second concurrent run"
        )
        self.source_document_id = source_document_id
        self.existing_run_id = existing_run_id


def _now() -> datetime:
    return datetime.now(UTC)


class RunStateService:
    """Persists run + step state for the pipeline orchestrator."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Run lifecycle ───────────────────────────────────────────────────

    async def find_active_run(self, source_document_id: UUID) -> IngestionRun | None:
        """Return the running ingestion_run for this source_document, if any."""
        result = await self._session.execute(
            select(IngestionRun)
            .where(
                IngestionRun.source_document_id == source_document_id,
                IngestionRun.status == RUN_RUNNING,
            )
            .order_by(IngestionRun.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def start_run(
        self,
        *,
        source_document_id: UUID,
        triggered_by: UUID | None = None,
    ) -> IngestionRun:
        """Create a fresh ingestion_run.

        Raises ConcurrentRunError if a run is already active for this document.
        Edge case (Pipeline W-7 §1, §7): two simultaneous starts ⇒ second fails.
        """
        existing = await self.find_active_run(source_document_id)
        if existing is not None:
            raise ConcurrentRunError(source_document_id, existing.id)
        run = IngestionRun(
            source_document_id=source_document_id,
            status=RUN_RUNNING,
            triggered_by=triggered_by,
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def get_run(self, run_id: UUID) -> IngestionRun | None:
        return await self._session.get(IngestionRun, run_id)

    async def complete_run(
        self,
        run_id: UUID,
        *,
        status: str,
        error_jsonb: dict[str, Any] | None = None,
    ) -> IngestionRun:
        """Finalize a run with succeeded / failed / partially_succeeded status."""
        if status not in (RUN_SUCCEEDED, RUN_FAILED, RUN_PARTIALLY_SUCCEEDED):
            raise ValueError(f"invalid terminal run status: {status!r}")
        run = await self.get_run(run_id)
        if run is None:
            raise ValueError(f"ingestion_run {run_id} not found")
        run.status = status
        run.completed_at = _now()
        if error_jsonb is not None:
            run.error_jsonb = error_jsonb
        await self._session.flush()
        return run

    async def find_resumable_run(self, source_document_id: UUID) -> IngestionRun | None:
        """Find a run for this document we should resume from rather than starting fresh.

        Picks the most recent run that is still 'running' (worker died mid-stage)
        or 'partially_succeeded' (Stage X failed, downstream not attempted).
        """
        result = await self._session.execute(
            select(IngestionRun)
            .where(
                IngestionRun.source_document_id == source_document_id,
                IngestionRun.status.in_((RUN_RUNNING, RUN_PARTIALLY_SUCCEEDED)),
            )
            .order_by(IngestionRun.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # ── Step lifecycle ──────────────────────────────────────────────────

    async def list_steps(self, run_id: UUID) -> list[IngestionRunStep]:
        result = await self._session.execute(
            select(IngestionRunStep)
            .where(IngestionRunStep.ingestion_run_id == run_id)
            .order_by(IngestionRunStep.started_at.nullslast(), IngestionRunStep.id)
        )
        return list(result.scalars().all())

    async def find_step(
        self,
        run_id: UUID,
        *,
        stage: str,
        input_match: dict[str, Any] | None = None,
    ) -> IngestionRunStep | None:
        """Look up a step by stage and (optionally) input_summary contents.

        For per-candidate Stage D steps, pass input_match={"candidate_id": "..."}
        — we match if every key/value in input_match is present in the step's
        input_summary_jsonb.
        """
        result = await self._session.execute(
            select(IngestionRunStep)
            .where(
                IngestionRunStep.ingestion_run_id == run_id,
                IngestionRunStep.stage == stage,
            )
            .order_by(IngestionRunStep.started_at.nullslast())
        )
        steps = list(result.scalars().all())
        if input_match is None:
            return steps[-1] if steps else None
        for step in steps:
            payload = step.input_summary_jsonb or {}
            if all(payload.get(k) == v for k, v in input_match.items()):
                return step
        return None

    async def start_step(
        self,
        *,
        run_id: UUID,
        stage: str,
        input_summary: dict[str, Any] | None = None,
    ) -> IngestionRunStep:
        """Create a new step row in 'running' status."""
        if stage not in ALL_STAGES:
            raise ValueError(f"unknown stage: {stage!r}")
        step = IngestionRunStep(
            ingestion_run_id=run_id,
            stage=stage,
            status=STEP_RUNNING,
            started_at=_now(),
            input_summary_jsonb=input_summary,
        )
        self._session.add(step)
        await self._session.flush()
        return step

    async def complete_step(
        self,
        step_id: UUID,
        *,
        output_summary: dict[str, Any] | None = None,
        llm_call_id: UUID | None = None,
    ) -> IngestionRunStep:
        step = await self._session.get(IngestionRunStep, step_id)
        if step is None:
            raise ValueError(f"ingestion_run_step {step_id} not found")
        step.status = STEP_SUCCEEDED
        step.completed_at = _now()
        if output_summary is not None:
            step.output_summary_jsonb = output_summary
        if llm_call_id is not None:
            step.llm_call_id = llm_call_id
        await self._session.flush()
        return step

    async def fail_step(
        self,
        step_id: UUID,
        *,
        error: dict[str, Any],
    ) -> IngestionRunStep:
        step = await self._session.get(IngestionRunStep, step_id)
        if step is None:
            raise ValueError(f"ingestion_run_step {step_id} not found")
        step.status = STEP_FAILED
        step.completed_at = _now()
        step.error_jsonb = error
        await self._session.flush()
        return step

    async def skip_step(
        self,
        *,
        run_id: UUID,
        stage: str,
        reason: str,
        input_summary: dict[str, Any] | None = None,
    ) -> IngestionRunStep:
        """Record that a stage was deliberately not run (e.g., Stage C produced
        zero candidates so per-candidate Stage D is skipped)."""
        step = IngestionRunStep(
            ingestion_run_id=run_id,
            stage=stage,
            status=STEP_SKIPPED,
            started_at=_now(),
            completed_at=_now(),
            input_summary_jsonb=input_summary,
            output_summary_jsonb={"skipped_reason": reason},
        )
        self._session.add(step)
        await self._session.flush()
        return step

    # ── Resume helpers ──────────────────────────────────────────────────

    async def is_stage_succeeded(
        self,
        run_id: UUID,
        *,
        stage: str,
        input_match: dict[str, Any] | None = None,
    ) -> bool:
        """True if the matching stage step for this run is in 'succeeded' state."""
        step = await self.find_step(run_id, stage=stage, input_match=input_match)
        return step is not None and step.status == STEP_SUCCEEDED
