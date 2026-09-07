"""Batch-wide candidate merge: load, LLM-merge, replace constituent rows."""

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from mc_contracts.errors import ErrorCode
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.auth.tenant_context import require_selected_tenant_id
from platform_service.config import get_settings
from platform_service.db.base import SessionLocal
from platform_service.db.models.ingestion_run import IngestionRun
from platform_service.db.models.module_candidate_draft import ModuleCandidateDraft
from platform_service.db.repositories.module_candidate_repository import (
    ModuleCandidateRepository,
)
from platform_service.db.repositories.source_repository import SourceRepository
from platform_service.localized import candidate_description_localized
from platform_service.services.candidate_merger import (
    CandidateMerger,
    CandidateMergerError,
    CandidateMergerResult,
    MergeGroup,
)
from platform_service.services.ingest_step_errors import build_step_failure
from platform_service.services.ingestion_cardinality import load_batch_for_run, resolve_from_batch
from platform_service.services.run_state_service import (
    RUN_RUNNING,
    STAGE_CANDIDATE_MERGE,
    STEP_FAILED,
    STEP_RUNNING,
    RunStateService,
)
from platform_service.services.token_estimation import estimate_token_count

logger = logging.getLogger(__name__)

_TOPIC_MERGED_FLAG = "topic_merged"


@dataclass(frozen=True)
class CandidateMergeSummary:
    """Audit record for one batch merge pass."""

    input_candidate_count: int
    group_count: int
    merged_candidate_count: int
    unmerged_candidate_count: int
    skipped: bool = False
    succeeded: bool = True


class CandidateMergeRunner:
    """Load batch candidates, merge same-topic groups, replace rows."""

    def __init__(
        self,
        session: AsyncSession | None = None,
        *,
        merger: CandidateMerger | None = None,
    ) -> None:
        self._session = session
        self._merger = merger or CandidateMerger()

    @classmethod
    async def run_staged(cls, batch_id: UUID, **kwargs: Any) -> CandidateMergeSummary:
        runner = cls(session=None, **kwargs)
        return await runner.run(batch_id)

    async def run(self, batch_id: UUID) -> CandidateMergeSummary:
        if self._session is not None:
            return await self._run_with_session(self._session, batch_id)

        prepared = await self._prepare(batch_id)
        if prepared is None:
            return CandidateMergeSummary(
                input_candidate_count=0,
                group_count=0,
                merged_candidate_count=0,
                unmerged_candidate_count=0,
                skipped=True,
                succeeded=True,
            )
        payloads, step_ids, primary_locale = prepared
        try:
            result = await self._merger.merge(payloads, primary_locale=primary_locale)
        except Exception as exc:
            logger.exception("Candidate merge LLM failed for batch_id=%s", batch_id)
            async with SessionLocal() as session:
                await self._fail_steps(session, step_ids, exc)
                await session.commit()
            if isinstance(exc, CandidateMergerError):
                raise
            raise CandidateMergerError(str(exc)) from exc

        async with SessionLocal() as session:
            summary = await self._finalize(session, batch_id, payloads, result, step_ids)
            await session.commit()
            return summary

    async def _run_with_session(self, session: AsyncSession, batch_id: UUID) -> CandidateMergeSummary:
        prepared = await self._prepare(batch_id, session=session)
        if prepared is None:
            return CandidateMergeSummary(
                input_candidate_count=0,
                group_count=0,
                merged_candidate_count=0,
                unmerged_candidate_count=0,
                skipped=True,
                succeeded=True,
            )
        payloads, step_ids, primary_locale = prepared
        try:
            result = await self._merger.merge(payloads, primary_locale=primary_locale)
        except Exception as exc:
            logger.exception("Candidate merge LLM failed for batch_id=%s", batch_id)
            await self._fail_steps(session, step_ids, exc)
            await session.commit()
            if isinstance(exc, CandidateMergerError):
                raise
            raise CandidateMergerError(str(exc)) from exc
        return await self._finalize(session, batch_id, payloads, result, step_ids)

    async def _prepare(
        self,
        batch_id: UUID,
        *,
        session: AsyncSession | None = None,
    ) -> tuple[list[dict[str, Any]], list[UUID], str] | None:
        if session is None:
            async with SessionLocal() as scoped:
                return await self._prepare(batch_id, session=scoped)

        run_state = RunStateService(session)
        participating = await _participating_runs(run_state, batch_id)
        if not participating:
            logger.info("Candidate merge: no identify-succeeded runs for batch_id=%s", batch_id)
            return None

        repo = ModuleCandidateRepository(session)
        drafts = await repo.list_candidates_for_runs([r.id for r in participating])
        run_by_id = {r.id: r for r in participating}
        excerpts = await _excerpts_for_drafts(session, drafts)
        payloads = [_draft_to_payload(d, run_by_id[d.ingestion_run_id], excerpts) for d in drafts]

        primary_locale = get_settings().deployment_primary_locale
        first_doc = await SourceRepository(session).get_source_document(participating[0].source_document_id)
        if first_doc is not None and first_doc.primary_language:
            primary_locale = first_doc.primary_language

        step_ids: list[UUID] = []
        for run in participating:
            step_id = await _ensure_merge_step_running(run_state, run.id, batch_id)
            step_ids.append(step_id)
        await session.commit()
        return payloads, step_ids, primary_locale

    async def _finalize(
        self,
        session: AsyncSession,
        batch_id: UUID,
        payloads: list[dict[str, Any]],
        result: CandidateMergerResult,
        step_ids: list[UUID],
    ) -> CandidateMergeSummary:
        run_state = RunStateService(session)
        repo = ModuleCandidateRepository(session)
        payload_by_id = {str(p["id"]): p for p in payloads}
        run_order = await _run_order_for_batch(run_state, batch_id)

        for group in result.groups:
            await _replace_group(
                session,
                repo,
                group,
                payload_by_id,
                run_order,
            )

        output = {
            "input_candidate_count": len(payloads),
            "group_count": len(result.groups),
            "merged_candidate_count": sum(len(g.constituent_ids) for g in result.groups),
            "unmerged_candidate_count": len(result.unmerged_ids),
        }
        for step_id in step_ids:
            await run_state.complete_step(step_id, output_summary=output)

        logger.info(
            "Candidate merge batch_id=%s groups=%d merged=%d unmerged=%d",
            batch_id,
            len(result.groups),
            output["merged_candidate_count"],
            output["unmerged_candidate_count"],
        )
        return CandidateMergeSummary(
            input_candidate_count=len(payloads),
            group_count=len(result.groups),
            merged_candidate_count=output["merged_candidate_count"],
            unmerged_candidate_count=len(result.unmerged_ids),
            skipped=False,
            succeeded=True,
        )

    async def _fail_steps(
        self,
        session: AsyncSession,
        step_ids: list[UUID],
        exc: Exception,
    ) -> None:
        run_state = RunStateService(session)
        user_message, error = build_step_failure(
            error_code=ErrorCode.CANDIDATE_MERGE_FAILED.value,
            exc=exc,
        )
        for step_id in step_ids:
            await run_state.fail_step(
                step_id,
                error_code=ErrorCode.CANDIDATE_MERGE_FAILED.value,
                error_message=user_message,
                error=error,
            )


async def _participating_runs(run_state: RunStateService, batch_id: UUID) -> list[IngestionRun]:
    runs = await run_state.list_runs_for_batch(batch_id)
    participating: list[IngestionRun] = []
    for run in runs:
        if run.status != RUN_RUNNING:
            continue
        if await run_state.is_module_identify_fully_succeeded(run.id):
            participating.append(run)
    return participating


async def _run_order_for_batch(run_state: RunStateService, batch_id: UUID) -> list[UUID]:
    runs = await run_state.list_runs_for_batch(batch_id)
    return [r.id for r in runs]


async def _ensure_merge_step_running(
    run_state: RunStateService,
    run_id: UUID,
    batch_id: UUID,
) -> UUID:
    existing = await run_state.find_step(run_id, stage=STAGE_CANDIDATE_MERGE)
    if existing is not None and existing.status in (STEP_RUNNING, STEP_FAILED):
        if existing.status == STEP_FAILED:
            await run_state.reset_step_for_retry(existing.id)
        return existing.id
    step = await run_state.start_step(
        run_id=run_id,
        stage=STAGE_CANDIDATE_MERGE,
        input_summary={"batch_id": str(batch_id)},
    )
    return step.id


def _draft_to_payload(
    draft: ModuleCandidateDraft,
    run: Any,
    excerpts: dict[UUID, str],
) -> dict[str, Any]:
    return {
        "id": draft.id,
        "ingestion_run_id": draft.ingestion_run_id,
        "source_document_id": run.source_document_id,
        "proposed_title": draft.proposed_title,
        "scope_summary": draft.scope_summary,
        "description_localized": draft.description_localized,
        "domain": draft.domain,
        "proposed_module_type": draft.proposed_module_type,
        "estimated_card_count": draft.estimated_card_count,
        "estimated_quiz_count": draft.estimated_quiz_count,
        "source_provenance": list(draft.source_provenance_jsonb or []),
        "quality_flags": dict(draft.quality_flags_jsonb or {}) if draft.quality_flags_jsonb else {},
        "source_chunk_ids": list(draft.source_chunk_ids or []),
        "chunk_ids": [str(c) for c in (draft.source_chunk_ids or [])],
        "clinical_review_notes": draft.clinical_review_notes,
        "previous_practice_summary": draft.previous_practice_summary,
        "current_practice_summary": draft.current_practice_summary,
        "rationale_summary": draft.rationale_summary,
        "ingestion_instruction_rationale": draft.ingestion_instruction_rationale,
        "excerpt": excerpts.get(draft.id, ""),
    }


async def _excerpts_for_drafts(
    session: AsyncSession,
    drafts: list[ModuleCandidateDraft],
) -> dict[UUID, str]:
    settings = get_settings()
    max_tokens = settings.candidate_merge_excerpt_max_tokens
    block_ids: list[UUID] = []
    for draft in drafts:
        for entry in draft.source_provenance_jsonb or []:
            if not isinstance(entry, dict):
                continue
            for raw in entry.get("content_block_ids") or []:
                try:
                    block_ids.append(UUID(str(raw)))
                except (TypeError, ValueError):
                    continue
    blocks = await SourceRepository(session).list_blocks_by_ids(block_ids)
    text_by_id = {b.id: b.content_text or "" for b in blocks}

    excerpts: dict[UUID, str] = {}
    for draft in drafts:
        parts: list[str] = []
        for entry in draft.source_provenance_jsonb or []:
            if not isinstance(entry, dict):
                continue
            for raw in entry.get("content_block_ids") or []:
                try:
                    bid = UUID(str(raw))
                except (TypeError, ValueError):
                    continue
                text = text_by_id.get(bid, "").strip()
                if text:
                    parts.append(text)
        combined = "\n\n".join(parts)
        excerpts[draft.id] = _truncate_excerpt(combined, max_tokens)
    return excerpts


def _truncate_excerpt(text: str, max_tokens: int) -> str:
    if max_tokens <= 0 or not text:
        return ""
    if estimate_token_count(text) <= max_tokens:
        return text
    # ~4 chars per token
    return text[: max(1, max_tokens * 4)].rstrip()


async def _replace_group(
    session: AsyncSession,
    repo: ModuleCandidateRepository,
    group: MergeGroup,
    payload_by_id: dict[str, dict[str, Any]],
    run_order: list[UUID],
) -> None:
    constituents = [payload_by_id[str(cid)] for cid in group.constituent_ids if str(cid) in payload_by_id]
    if len(constituents) < 2:
        return

    home_run_id = _home_run_id(constituents, run_order)
    home_source_id = next(
        c["source_document_id"] for c in constituents if c["ingestion_run_id"] == home_run_id
    )

    merged_prov: list[dict[str, Any]] = []
    seen_blocks: set[tuple[str, str, str]] = set()
    chunk_refs: list[dict[str, str]] = []
    seen_refs: set[tuple[str, str]] = set()
    constituent_titles: list[str] = []
    home_chunk_ids: list[str] = []

    for c in constituents:
        constituent_titles.append(str(c.get("proposed_title") or ""))
        source_id = str(c["source_document_id"])
        for chunk_id in c.get("chunk_ids") or []:
            key = (source_id, str(chunk_id))
            if key in seen_refs:
                continue
            seen_refs.add(key)
            chunk_refs.append({"source_document_id": source_id, "chunk_id": str(chunk_id)})
            if c["ingestion_run_id"] == home_run_id:
                home_chunk_ids.append(str(chunk_id))
        for entry in c.get("source_provenance") or []:
            if not isinstance(entry, dict):
                continue
            doc = str(entry.get("source_document_id") or "")
            page = str(entry.get("source_page_id") or "")
            for block in entry.get("content_block_ids") or []:
                tup = (doc, page, str(block))
                if tup in seen_blocks:
                    continue
                seen_blocks.add(tup)
                merged_prov.append(
                    {
                        "source_document_id": entry.get("source_document_id"),
                        "source_page_id": entry.get("source_page_id"),
                        "content_block_ids": [block],
                    }
                )

    first = constituents[0]
    batch = await load_batch_for_run(session, home_run_id)
    cardinality = resolve_from_batch(batch)
    card_count = (
        cardinality.target_cards
        if cardinality.target_cards is not None
        else max(int(c.get("estimated_card_count") or 0) for c in constituents)
    )
    quiz_count = (
        cardinality.target_quizzes
        if cardinality.target_quizzes is not None
        else max(int(c.get("estimated_quiz_count") or 0) for c in constituents)
    )

    flags = list((first.get("quality_flags") or {}).get("flags") or [])
    if _TOPIC_MERGED_FLAG not in flags:
        flags.append(_TOPIC_MERGED_FLAG)
    quality_flags = {
        "flags": flags,
        "merge_lineage": {
            "constituent_candidate_ids": [str(cid) for cid in group.constituent_ids],
            "constituent_titles": constituent_titles,
            "pairing_rationale": group.pairing_rationale,
            "chunk_refs": chunk_refs,
            "home_source_document_id": str(home_source_id),
        },
    }

    for cid in group.constituent_ids:
        await repo.delete_candidate(cid)

    await repo.create_candidate(
        ingestion_run_id=home_run_id,
        proposed_title=group.merged_title,
        scope_summary=group.merged_scope_summary,
        description_localized=candidate_description_localized(
            {"proposed_title": group.merged_title, "scope_summary": group.merged_scope_summary}
        ),
        domain=first.get("domain"),
        source_provenance=merged_prov,
        estimated_card_count=card_count,
        estimated_quiz_count=quiz_count,
        proposed_module_type=str(first.get("proposed_module_type") or "refresher"),
        quality_flags=quality_flags,
        clinical_review_notes=first.get("clinical_review_notes"),
        previous_practice_summary=first.get("previous_practice_summary"),
        current_practice_summary=first.get("current_practice_summary"),
        rationale_summary=first.get("rationale_summary"),
        ingestion_instruction_rationale=first.get("ingestion_instruction_rationale"),
        source_chunk_ids=home_chunk_ids or None,
        tenant_id=require_selected_tenant_id(),
    )


def _home_run_id(constituents: list[dict[str, Any]], run_order: list[UUID]) -> UUID:
    constituent_runs = {c["ingestion_run_id"] for c in constituents}
    for run_id in run_order:
        if run_id in constituent_runs:
            return run_id
    return constituents[0]["ingestion_run_id"]
