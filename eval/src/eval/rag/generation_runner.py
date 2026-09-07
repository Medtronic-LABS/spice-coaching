"""Generate RAG answers from pre-retrieved modules (BM25, embedding, etc.)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import UUID

from platform_service.db.models.module import Module
from platform_service.integrations.ai_runtime_client import AIRuntimeClient
from platform_service.services.card_normalisation import card_row_to_dict
from platform_service.services.coaching_rag_errors import CoachingRagError
from platform_service.services.coaching_rag_service import CoachingRagService, parse_rag_json
from platform_service.services.llm_text_utils import format_grounded_rag_answer
from sqlalchemy.ext.asyncio import AsyncSession

from eval.rag.rag_runner import EvalObjectStorage


@dataclass(frozen=True)
class RetrievalGenerationResult:
    answer: str
    model: str | None
    generation_context: str
    cited_module_ids: list[str]
    suggested_questions: list[str]
    generate_latency_ms: float | None
    error: str | None


async def generate_answer_for_module_pairs(
    session: AsyncSession,
    ai: AIRuntimeClient,
    *,
    question: str,
    language: str,
    pairs: list[tuple[Module, float]],
    cards_by_module: dict[UUID, list[dict[str, object]]],
) -> RetrievalGenerationResult:
    if not pairs:
        return RetrievalGenerationResult(
            answer="",
            model=None,
            generation_context="",
            cited_module_ids=[],
            suggested_questions=[],
            generate_latency_ms=None,
            error="no retrieved modules for generation",
        )

    storage = EvalObjectStorage()
    service = CoachingRagService(session, ai, storage)
    context = service.build_retrieval_context(pairs, cards_by_module=cards_by_module)

    started = time.perf_counter()
    try:
        response = await service.generate_answer(
            question=question,
            context=context,
            lang=language,
            use_local=False,
        )
    except CoachingRagError as exc:
        return RetrievalGenerationResult(
            answer="",
            model=None,
            generation_context=context,
            cited_module_ids=[],
            suggested_questions=[],
            generate_latency_ms=(time.perf_counter() - started) * 1000.0,
            error=exc.message,
        )
    except Exception as exc:
        return RetrievalGenerationResult(
            answer="",
            model=None,
            generation_context=context,
            cited_module_ids=[],
            suggested_questions=[],
            generate_latency_ms=(time.perf_counter() - started) * 1000.0,
            error=str(exc),
        )

    generate_ms = (time.perf_counter() - started) * 1000.0
    if response.error:
        return RetrievalGenerationResult(
            answer="",
            model=response.model,
            generation_context=context,
            cited_module_ids=[],
            suggested_questions=[],
            generate_latency_ms=generate_ms,
            error=response.error,
        )

    try:
        payload = parse_rag_json(response.raw_text, response.parsed_json)
        answer = format_grounded_rag_answer((payload.get("answer") or "").strip())
        if not answer:
            raise CoachingRagError("model JSON missing non-empty 'answer' field")
        cited_ids = [
            str(module_id)
            for module_id in CoachingRagService._parse_cited_module_ids(payload.get("cited_module_ids") or [])
        ]
        suggested = [
            str(item)
            for item in CoachingRagService._parse_suggested_questions(payload.get("suggested_questions"))
        ]
    except CoachingRagError as exc:
        return RetrievalGenerationResult(
            answer="",
            model=response.model,
            generation_context=context,
            cited_module_ids=[],
            suggested_questions=[],
            generate_latency_ms=generate_ms,
            error=exc.message,
        )

    return RetrievalGenerationResult(
        answer=answer,
        model=response.model,
        generation_context=context,
        cited_module_ids=cited_ids,
        suggested_questions=suggested,
        generate_latency_ms=generate_ms,
        error=None,
    )


def card_rows_to_dict_map(
    card_rows: list[object],
) -> dict[UUID, list[dict[str, object]]]:
    cards_by_module: dict[UUID, list[dict[str, object]]] = {}
    for row in card_rows:
        module_id = getattr(row, "module_id", None)
        if module_id is None:
            continue
        cards_by_module.setdefault(module_id, []).append(card_row_to_dict(row))
    return cards_by_module
