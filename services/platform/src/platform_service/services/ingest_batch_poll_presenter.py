"""Build tree-shaped ingest batch poll payloads for the admin UI."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.config import get_settings
from platform_service.db.models.hierarchy_user import HierarchyUser
from platform_service.db.models.ingestion_run import IngestionRun, IngestionRunStep
from platform_service.db.models.module_candidate_draft import ModuleCandidateDraft
from platform_service.db.models.source_document import SourceDocument
from platform_service.db.repositories.hierarchy_repository import HierarchyRepository
from platform_service.db.repositories.module_candidate_repository import (
    ModuleCandidateRepository,
)
from platform_service.services.ingest_progress_catalog import (
    candidate_catalog_entry,
    catalog_entry,
    chunk_catalog_entry,
)
from platform_service.services.ingest_run_error_summary import (
    summarize_batch_error,
    summarize_error_from_failed_children,
    summarize_ingestion_run_error,
)
from platform_service.services.ingestion_run_presenter import IngestionRunPresenter
from platform_service.services.run_state.steps import is_module_identify_chunk_step
from platform_service.services.run_state_service import (
    POST_PUBLISH_STAGES,
    RUN_FAILED,
    RUN_PARTIALLY_SUCCEEDED,
    RUN_RUNNING,
    STAGE_CARD_DRAFT,
    STAGE_EXTRACT,
    STAGE_MODULE_IDENTIFY,
    STAGE_THUMBNAIL,
    STEP_AWAITING_INPUT,
    STEP_FAILED,
    STEP_PENDING,
    STEP_RUNNING,
    STEP_SKIPPED,
    STEP_SUCCEEDED,
    RunStateService,
)

_PREFIX_STAGE_ORDER = (STAGE_THUMBNAIL, STAGE_EXTRACT)
_SHARED_STAGE_ORDER = (*_PREFIX_STAGE_ORDER, STAGE_MODULE_IDENTIFY)
_CANDIDATE_STAGE_ORDER = (STAGE_CARD_DRAFT, *POST_PUBLISH_STAGES)


def _document_label(doc: SourceDocument | None) -> str:
    if doc is None:
        return ""
    filename = (doc.original_filename or "").strip()
    if filename:
        return filename
    return doc.title


def _actor_ref(user_id: int | None, users_by_id: dict[int, HierarchyUser]) -> dict[str, Any] | None:
    if user_id is None:
        return None
    user = users_by_id.get(user_id)
    if user is None:
        return None
    return {"id": user.id, "name": user.name}


def _candidate_id_from_step(step: IngestionRunStep) -> str | None:
    summary = step.input_summary_jsonb or {}
    raw = summary.get("candidate_id")
    return str(raw) if raw else None


def _step_node(step: IngestionRunStep) -> dict[str, Any]:
    poll = IngestionRunPresenter.step_to_poll_dict(step)
    activity = poll.get("activity")
    catalog_activity = activity if isinstance(activity, str) else None
    title, description = catalog_entry(step.stage, activity=catalog_activity)
    node: dict[str, Any] = {
        "key": step.stage,
        "title": title,
        "description": description,
        "status": step.status,
        "started_at": step.started_at.isoformat() if step.started_at else None,
        "completed_at": step.completed_at.isoformat() if step.completed_at else None,
        "error": step.error_jsonb,
        "error_code": step.error_code,
        "error_message": poll.get("error_message"),
        "children": [],
    }
    if activity:
        node["activity"] = activity
    if "published_module_merge" in poll:
        node["published_module_merge"] = poll["published_module_merge"]
    if step.input_summary_jsonb is not None:
        node["input_summary"] = step.input_summary_jsonb
    if step.output_summary_jsonb is not None:
        # Strip bulky card stashes from poll; worker still reads full step jsonb.
        output = dict(step.output_summary_jsonb)
        output.pop("new_cards", None)
        output.pop("merged_cards", None)
        node["output_summary"] = output
    return node


def _sort_steps(steps: list[IngestionRunStep], order: tuple[str, ...]) -> list[IngestionRunStep]:
    rank = {stage: idx for idx, stage in enumerate(order)}
    return sorted(
        steps,
        key=lambda s: (
            rank.get(s.stage, len(order)),
            s.started_at.timestamp() if s.started_at else 0.0,
            str(s.id),
        ),
    )


def _chunk_id_from_step(step: IngestionRunStep) -> str | None:
    summary = step.input_summary_jsonb or {}
    raw = summary.get("chunk_id")
    return str(raw) if raw else None


def _chunk_node(step: IngestionRunStep) -> dict[str, Any]:
    chunk_id = _chunk_id_from_step(step) or "chunk"
    title, description = chunk_catalog_entry(chunk_id)
    node: dict[str, Any] = {
        "key": "chunk",
        "title": title,
        "description": description,
        "status": step.status,
        "chunk_id": chunk_id,
        "started_at": step.started_at.isoformat() if step.started_at else None,
        "completed_at": step.completed_at.isoformat() if step.completed_at else None,
        "error": step.error_jsonb,
        "error_code": step.error_code,
        "error_message": IngestionRunPresenter._present_step_error_message(step),
        "children": [],
    }
    if step.input_summary_jsonb is not None:
        node["input_summary"] = step.input_summary_jsonb
    if step.output_summary_jsonb is not None:
        node["output_summary"] = step.output_summary_jsonb
    return node


def _chunk_ids_for_source(cand: ModuleCandidateDraft, source_document_id: UUID) -> list[str]:
    """Chunk ids on this source that should show ``cand`` in the poll tree."""
    flags = cand.quality_flags_jsonb or {}
    lineage = flags.get("merge_lineage") or {}
    refs = lineage.get("chunk_refs") or []
    if isinstance(refs, list) and refs:
        source_str = str(source_document_id)
        out: list[str] = []
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            if str(ref.get("source_document_id")) != source_str:
                continue
            chunk_id = ref.get("chunk_id")
            if chunk_id:
                out.append(str(chunk_id))
        return out
    return [str(x) for x in (cand.source_chunk_ids or []) if x]


def _candidate_visible_on_source(cand: ModuleCandidateDraft, source_document_id: UUID) -> bool:
    if _chunk_ids_for_source(cand, source_document_id):
        return True
    for entry in cand.source_provenance_jsonb or []:
        if isinstance(entry, dict) and str(entry.get("source_document_id")) == str(source_document_id):
            return True
    return False


def build_run_tree(
    *,
    steps: list[IngestionRunStep],
    candidates: list[ModuleCandidateDraft],
    source_document_id: UUID,
    candidate_steps: dict[str, list[IngestionRunStep]] | None = None,
) -> list[dict[str, Any]]:
    """Assemble progressed-only nodes for one pipeline run."""
    prefix = [s for s in steps if s.stage in _PREFIX_STAGE_ORDER]
    nodes = [_step_node(s) for s in _sort_steps(prefix, _PREFIX_STAGE_ORDER)]

    by_candidate: dict[str, list[IngestionRunStep]] = dict(candidate_steps or {})
    if not by_candidate:
        for step in steps:
            if step.stage not in _CANDIDATE_STAGE_ORDER:
                continue
            cand_id = _candidate_id_from_step(step)
            if cand_id is None:
                continue
            by_candidate.setdefault(cand_id, []).append(step)

    visible = [c for c in candidates if _candidate_visible_on_source(c, source_document_id)]
    candidates_by_id = {str(c.id): c for c in visible}
    ordered_ids = [str(c.id) for c in visible]
    for cand_id in by_candidate:
        if cand_id not in ordered_ids and cand_id in {str(c.id) for c in candidates}:
            cand = next((c for c in candidates if str(c.id) == cand_id), None)
            if cand is not None and _candidate_visible_on_source(cand, source_document_id):
                ordered_ids.append(cand_id)
                candidates_by_id[cand_id] = cand

    identify_all = [s for s in steps if s.stage == STAGE_MODULE_IDENTIFY]
    parent_steps = [s for s in identify_all if not is_module_identify_chunk_step(s)]
    chunk_steps = [s for s in identify_all if is_module_identify_chunk_step(s)]
    chunk_nodes = [_chunk_node(s) for s in _sort_steps(chunk_steps, (STAGE_MODULE_IDENTIFY,))]
    chunks_by_id = {str(n["chunk_id"]): n for n in chunk_nodes}

    for cand_id in ordered_ids:
        cand = candidates_by_id.get(cand_id)
        if cand is None:
            continue
        chunk_ids = _chunk_ids_for_source(cand, source_document_id)
        if not chunk_ids:
            continue
        proposed = cand.proposed_title if cand is not None else ""
        title, description = candidate_catalog_entry(proposed)
        child_steps = _sort_steps(by_candidate.get(cand_id, []), _CANDIDATE_STAGE_ORDER)
        child_nodes = [_step_node(s) for s in child_steps]
        status = _candidate_branch_status(child_steps) if child_steps else STEP_PENDING
        started = child_steps[0].started_at.isoformat() if child_steps and child_steps[0].started_at else None
        branch_base = {
            "key": "candidate",
            "title": title,
            "description": description,
            "status": status,
            "candidate_id": cand_id,
            "proposed_title": proposed or None,
            "started_at": started,
            "completed_at": None,
            "error": None,
            "children": child_nodes,
        }
        if branch_base["status"] == "partially_succeeded" and not branch_base.get("error"):
            branch_base["error"] = summarize_error_from_failed_children(child_nodes)
        for chunk_id in chunk_ids:
            chunk_node = chunks_by_id.get(chunk_id)
            if chunk_node is None:
                continue
            chunk_node["children"].append(dict(branch_base))

    for chunk_node in chunk_nodes:
        identify_status = str(chunk_node["status"])
        nested_statuses = [str(b["status"]) for b in chunk_node["children"]]
        chunk_node["status"] = _rollup_statuses([identify_status, *nested_statuses])
        if chunk_node["status"] == "partially_succeeded" and not chunk_node.get("error"):
            chunk_node["error"] = summarize_error_from_failed_children(chunk_node["children"])

    identify_node: dict[str, Any] | None = None
    if parent_steps:
        identify_node = _step_node(_sort_steps(parent_steps, (STAGE_MODULE_IDENTIFY,))[0])
    elif chunk_nodes:
        title, description = catalog_entry(STAGE_MODULE_IDENTIFY)
        identify_node = {
            "key": STAGE_MODULE_IDENTIFY,
            "title": title,
            "description": description,
            "status": STEP_PENDING,
            "started_at": None,
            "completed_at": None,
            "error": None,
            "children": [],
        }

    if identify_node is not None:
        identify_node["children"] = chunk_nodes
        if chunk_nodes:
            identify_node["status"] = _rollup_statuses([str(n["status"]) for n in chunk_nodes])
            if identify_node["status"] == "partially_succeeded" and not identify_node.get("error"):
                identify_node["error"] = summarize_error_from_failed_children(chunk_nodes)
        nodes.append(identify_node)

    covered = set(_SHARED_STAGE_ORDER) | set(_CANDIDATE_STAGE_ORDER)
    extras = [s for s in steps if s.stage not in covered]
    for step in sorted(
        extras,
        key=lambda s: (s.started_at.timestamp() if s.started_at else 0.0, str(s.id)),
    ):
        nodes.append(_step_node(step))

    return nodes


def _rollup_statuses(statuses: list[str]) -> str:
    if any(s == STEP_RUNNING for s in statuses):
        return STEP_RUNNING
    if any(s == STEP_AWAITING_INPUT for s in statuses):
        return STEP_AWAITING_INPUT
    if any(s == STEP_PENDING for s in statuses):
        return STEP_PENDING
    if statuses and all(s == STEP_SUCCEEDED for s in statuses):
        return STEP_SUCCEEDED
    if statuses and all(s == STEP_FAILED for s in statuses):
        return STEP_FAILED
    if statuses and all(s in (STEP_SUCCEEDED, STEP_FAILED, STEP_SKIPPED) for s in statuses):
        if any(s == STEP_FAILED for s in statuses):
            return "partially_succeeded"
        return STEP_SUCCEEDED
    return statuses[-1] if statuses else STEP_PENDING


def _candidate_branch_status(steps: list[IngestionRunStep]) -> str:
    return _rollup_statuses([s.status for s in steps])


def _retry_targets_for_run(
    *,
    batch_id: UUID,
    run: IngestionRun,
    steps: list[IngestionRunStep],
    blocked_by_active_claim: bool,
) -> list[dict[str, Any]]:
    """Build POST bodies for failed steps the retry API would accept (not noop)."""
    if blocked_by_active_claim:
        return []

    targets: list[dict[str, Any]] = []
    for step in steps:
        if step.status != STEP_FAILED:
            continue
        entry: dict[str, Any] = {
            "run_id": str(run.id),
            "stage": step.stage,
        }
        summary = step.input_summary_jsonb or {}
        candidate_id = summary.get("candidate_id")
        if candidate_id:
            entry["candidate_id"] = str(candidate_id)
        chunk_id = summary.get("chunk_id")
        if chunk_id:
            entry["chunk_id"] = str(chunk_id)
        targets.append(entry)
    return targets


class IngestBatchPollPresenter:
    """JSON payload for ``GET /admin/ingest/batches/{batch_id}``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._state = RunStateService(session)
        self._candidate_repo = ModuleCandidateRepository(session)

    async def present_batch(self, batch_id: UUID) -> dict[str, Any] | None:
        batch = await self._state.refresh_batch_status(batch_id)
        if batch is None:
            return None

        runs = await self._state.list_runs_for_batch(batch_id)

        doc_ids = list({r.source_document_id for r in runs})
        docs_by_id: dict[UUID, SourceDocument] = {}
        if doc_ids:
            docs_result = await self._session.execute(
                select(SourceDocument).where(SourceDocument.id.in_(doc_ids))
            )
            docs_by_id = {d.id: d for d in docs_result.scalars().all()}

        all_candidates = await self._candidate_repo.list_candidates_for_runs([r.id for r in runs])
        steps_by_run: dict[UUID, list[IngestionRunStep]] = {}
        candidate_steps: dict[str, list[IngestionRunStep]] = {}
        for run in runs:
            steps = await self._state.list_steps(run.id)
            steps_by_run[run.id] = steps
            for step in steps:
                if step.stage not in _CANDIDATE_STAGE_ORDER:
                    continue
                cand_id = _candidate_id_from_step(step)
                if cand_id is None:
                    continue
                candidate_steps.setdefault(cand_id, []).append(step)

        sources: list[dict[str, Any]] = []
        retries: list[dict[str, Any]] = []
        source_errors: list[dict[str, Any] | None] = []
        document_labels: list[str] = []
        for run in runs:
            steps = steps_by_run[run.id]
            blocked = run.status == RUN_RUNNING and self._state.has_active_pipeline_claim(run)
            label = _document_label(docs_by_id.get(run.source_document_id))
            run_error = summarize_ingestion_run_error(
                run.error_jsonb,
                steps=steps,
                status=run.status,
            )
            sources.append(
                {
                    "source_document_id": str(run.source_document_id),
                    "run_id": str(run.id),
                    "document_label": label,
                    "status": run.status,
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                    "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                    "error": run_error,
                    "nodes": build_run_tree(
                        steps=steps,
                        candidates=all_candidates,
                        source_document_id=run.source_document_id,
                        candidate_steps=candidate_steps,
                    ),
                }
            )
            if run.status in (RUN_PARTIALLY_SUCCEEDED, RUN_FAILED):
                source_errors.append(run_error)
            else:
                source_errors.append(None)
            document_labels.append(label)
            retries.extend(
                _retry_targets_for_run(
                    batch_id=batch_id,
                    run=run,
                    steps=steps,
                    blocked_by_active_claim=blocked,
                )
            )

        users_by_id: dict[int, HierarchyUser] = {}
        if batch.ingested_by is not None:
            users_by_id = await HierarchyRepository(self._session).get_users_by_ids([batch.ingested_by])

        batch_error = summarize_batch_error(
            batch.status,
            source_errors,
            document_labels=document_labels,
        )
        if batch_error is None and batch.error_jsonb:
            batch_error = summarize_ingestion_run_error(batch.error_jsonb, status=batch.status)

        payload: dict[str, Any] = {
            "batch_id": str(batch.id),
            "status": batch.status,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
            "error": batch_error,
            "ingested_by": _actor_ref(batch.ingested_by, users_by_id),
            "sources": sources,
            "retry_url": (
                get_settings().api_path(f"/admin/ingest/batches/{batch_id}/retry") if retries else None
            ),
        }
        return payload
