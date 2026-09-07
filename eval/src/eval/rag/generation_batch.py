"""Batch retrieval + LLM answer generation for BM25/embedding eval paths."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from platform_service.auth.tenant_context import using_selected_tenant
from platform_service.db.base import SessionLocal
from platform_service.db.models.module import Module
from platform_service.db.repositories.module_repository import ModuleRepository
from platform_service.integrations.ai_runtime_client import AIRuntimeClient
from platform_service.services.card_normalisation import card_row_to_dict
from sqlalchemy.ext.asyncio import AsyncSession

from eval.rag.answer_metrics import (
    artifact_category_slug,
    compute_e2e_metrics,
    compute_retrieval_metrics,
)
from eval.rag.bm25 import Bm25Index, Hit
from eval.rag.checkpoint import CheckpointContext, EvalRunProgress, after_record
from eval.rag.citation_metrics import compute_citation_metrics
from eval.rag.context_metrics import compute_context_metrics
from eval.rag.corpus import CardCorpusDoc
from eval.rag.embedding import EmbeddingHit, EmbeddingRetriever
from eval.rag.generation_runner import RetrievalGenerationResult, generate_answer_for_module_pairs
from eval.rag.rag_dataset import RagGoldenRecord


@dataclass(frozen=True)
class GenerationBatchConfig:
    retrieval_method: str
    dataset_path: Path
    k: int
    tenant_id: int | None
    ai_runtime_url: str
    ai_runtime_token: str
    run_id: str | None = None


def _pairs_from_bm25_hits(
    hits: list[Hit],
    modules_by_id: dict[UUID, Module],
) -> list[tuple[Module, float]]:
    pairs: list[tuple[Module, float]] = []
    for hit in hits:
        module = modules_by_id.get(hit.module_id)
        if module is None:
            continue
        pairs.append((module, -hit.bm25_score))
    return pairs


def _pairs_from_embedding_hits(
    hits: list[EmbeddingHit],
    modules_by_id: dict[UUID, Module],
) -> list[tuple[Module, float]]:
    pairs: list[tuple[Module, float]] = []
    for hit in hits:
        module = modules_by_id.get(hit.module_id)
        if module is None:
            continue
        pairs.append((module, hit.cosine_distance))
    return pairs


async def _load_cards_dict_by_module(
    session: AsyncSession,
    module_ids: list[UUID],
) -> dict[UUID, list[dict[str, object]]]:
    card_rows = await ModuleRepository(session).list_cards_for_module_ids(module_ids)
    cards_by_module: dict[UUID, list[dict[str, object]]] = {}
    for row in card_rows:
        if row.module_id is None:
            continue
        cards_by_module.setdefault(row.module_id, []).append(card_row_to_dict(row))
    return cards_by_module


def _artifact_from_generation(
    *,
    record: RagGoldenRecord,
    retrieval_method: str,
    retrieved_module_ids: list[str],
    retrieval_scores: list[float],
    generation: RetrievalGenerationResult,
    k: int,
    retrieved_uuids: list[UUID],
    cited_uuids: list[UUID],
    cards_by_module: dict[UUID, list[CardCorpusDoc]],
) -> dict[str, object]:
    context_text = generation.generation_context
    e2e_metrics = compute_e2e_metrics(
        record=record,
        answer=generation.answer,
        cited_module_ids=cited_uuids,
        retrieved_module_ids=retrieved_uuids,
        error=generation.error,
        context_text=context_text,
    )
    return {
        "id": record.id,
        "category": record.category,
        "category_slug": artifact_category_slug(record),
        "language": record.language,
        "query": record.query,
        "expected_answer": record.expected_answer,
        "expected_module_ids": [str(module_id) for module_id in record.expected_module_ids],
        "expected_card_ids": [str(card_id) for card_id in record.expected_card_ids],
        "answerable": record.answerable,
        "is_out_of_scope": record.is_out_of_scope,
        "answer": generation.answer,
        "model": generation.model,
        "generation_context": generation.generation_context,
        "retrieved_module_ids": retrieved_module_ids,
        "cited_module_ids": generation.cited_module_ids,
        "suggested_questions": generation.suggested_questions,
        "retrieval_scores": retrieval_scores,
        "latency_ms": {"generate": generation.generate_latency_ms},
        "error": generation.error,
        "retrieval_method": retrieval_method,
        "e2e_metrics": e2e_metrics,
        "retrieval_metrics": compute_retrieval_metrics(
            record=record,
            retrieved_module_ids=retrieved_uuids,
            cosine_distances=retrieval_scores,
            k=k,
        )
        or {},
        "context_metrics": compute_context_metrics(
            record=record,
            retrieved_module_ids=retrieved_uuids,
            cards_by_module=cards_by_module,
            k=k,
        )
        or {},
        "citation_metrics": compute_citation_metrics(
            record=record,
            answer=generation.answer,
            cited_module_ids=cited_uuids,
            retrieved_module_ids=retrieved_uuids,
        ),
        "judge_metrics": {},
        "exact_match": e2e_metrics.get("exact_match"),
        "token_f1": e2e_metrics.get("token_f1"),
        "token_recall": e2e_metrics.get("token_recall"),
        "abstention_correct": e2e_metrics.get("abstention_correct"),
        "citation_accuracy": e2e_metrics.get("citation_accuracy"),
        "safety_pass": e2e_metrics.get("safety_pass"),
        "partial_answer_correct": e2e_metrics.get("partial_answer_correct"),
        "answer_grounding_overlap": e2e_metrics.get("answer_grounding_overlap"),
    }


async def run_bm25_generation_batch(
    *,
    records: list[RagGoldenRecord],
    config: GenerationBatchConfig,
    index: Bm25Index,
    modules: list[Module],
    cards_by_module: dict[UUID, list[CardCorpusDoc]],
    progress: EvalRunProgress,
    checkpoint_ctx: CheckpointContext,
) -> None:
    modules_by_id = {module.id: module for module in modules}
    ai = AIRuntimeClient(base_url=config.ai_runtime_url, token=config.ai_runtime_token)
    try:
        async with SessionLocal() as session:
            tenant_scope = (
                using_selected_tenant(config.tenant_id) if config.tenant_id is not None else nullcontext()
            )
            with tenant_scope:
                for record in records:
                    if progress.should_skip(record.id):
                        continue
                    hits = index.search(record.query, k=config.k)
                    pairs = _pairs_from_bm25_hits(hits, modules_by_id)
                    module_ids = [module.id for module, _ in pairs]
                    cards_dict = await _load_cards_dict_by_module(session, module_ids)
                    generation = await generate_answer_for_module_pairs(
                        session,
                        ai,
                        question=record.query,
                        language=record.language,
                        pairs=pairs,
                        cards_by_module=cards_dict,
                    )
                    retrieved_module_ids = [str(hit.module_id) for hit in hits]
                    retrieval_scores = [-hit.bm25_score for hit in hits]
                    retrieved_uuids = [UUID(module_id) for module_id in retrieved_module_ids]
                    cited_uuids = [UUID(module_id) for module_id in generation.cited_module_ids]
                    artifact = _artifact_from_generation(
                        record=record,
                        retrieval_method="bm25",
                        retrieved_module_ids=retrieved_module_ids,
                        retrieval_scores=retrieval_scores,
                        generation=generation,
                        k=config.k,
                        retrieved_uuids=retrieved_uuids,
                        cited_uuids=cited_uuids,
                        cards_by_module=cards_by_module,
                    )
                    after_record(
                        progress,
                        record.id,
                        artifact=artifact,
                        checkpoint_ctx=checkpoint_ctx,
                    )
    finally:
        await ai.aclose()


async def run_embedding_generation_batch(
    *,
    records: list[RagGoldenRecord],
    config: GenerationBatchConfig,
    modules: list[Module],
    cards_by_module: dict[UUID, list[CardCorpusDoc]],
    retriever: EmbeddingRetriever,
    progress: EvalRunProgress,
    checkpoint_ctx: CheckpointContext,
) -> None:
    modules_by_id = {module.id: module for module in modules}
    ai = AIRuntimeClient(base_url=config.ai_runtime_url, token=config.ai_runtime_token)
    try:
        async with SessionLocal() as session:
            tenant_scope = (
                using_selected_tenant(config.tenant_id) if config.tenant_id is not None else nullcontext()
            )
            with tenant_scope:
                for record in records:
                    if progress.should_skip(record.id):
                        continue
                    hits = await retriever.search(record.query, k=config.k)
                    pairs = _pairs_from_embedding_hits(hits, modules_by_id)
                    module_ids = [module.id for module, _ in pairs]
                    cards_dict = await _load_cards_dict_by_module(session, module_ids)
                    generation = await generate_answer_for_module_pairs(
                        session,
                        ai,
                        question=record.query,
                        language=record.language,
                        pairs=pairs,
                        cards_by_module=cards_dict,
                    )
                    retrieved_module_ids = [str(hit.module_id) for hit in hits]
                    retrieval_scores = [hit.cosine_distance for hit in hits]
                    retrieved_uuids = [UUID(module_id) for module_id in retrieved_module_ids]
                    cited_uuids = [UUID(module_id) for module_id in generation.cited_module_ids]
                    artifact = _artifact_from_generation(
                        record=record,
                        retrieval_method="embedding",
                        retrieved_module_ids=retrieved_module_ids,
                        retrieval_scores=retrieval_scores,
                        generation=generation,
                        k=config.k,
                        retrieved_uuids=retrieved_uuids,
                        cited_uuids=cited_uuids,
                        cards_by_module=cards_by_module,
                    )
                    after_record(
                        progress,
                        record.id,
                        artifact=artifact,
                        checkpoint_ctx=checkpoint_ctx,
                    )
    finally:
        await ai.aclose()


def _as_dict(val: object) -> dict[str, object]:
    return dict(val) if isinstance(val, dict) else {}


def build_generation_batch_report(
    *,
    config: GenerationBatchConfig,
    artifacts: list[dict[str, object]],
    corpus_published_count: int,
    corpus_embedded_count: int | None,
    e2e_summary: dict[str, object],
) -> dict[str, object]:
    run_id = config.run_id or datetime.now(UTC).strftime(f"{config.retrieval_method}-gen-%Y%m%d-%H%M%S")
    retrieval_summary = _as_dict(e2e_summary.get("retrieval_summary"))
    return {
        "run_id": run_id,
        "retrieval_method": config.retrieval_method,
        "dataset_path": str(config.dataset_path),
        "k": config.k,
        "corpus_published_count": corpus_published_count,
        "corpus_embedded_count": corpus_embedded_count,
        "record_count": len(artifacts),
        "evaluated_record_count": len(artifacts),
        "e2e_summary": e2e_summary,
        "retrieval_summary": retrieval_summary,
        "context_summary": _as_dict(e2e_summary.get("context_summary")),
        "citation_summary": _as_dict(e2e_summary.get("citation_summary")),
        "judge_summary": _as_dict(e2e_summary.get("judge_summary")),
        "artifacts": artifacts,
        "generated_at": datetime.now(UTC).isoformat(),
    }
