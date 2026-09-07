"""In-process runner for RAG chatbot end-to-end evaluation."""

from __future__ import annotations

import time
from contextlib import nullcontext
from dataclasses import dataclass
from uuid import UUID

from mc_contracts.coaching import CoachingLocalRagRequest, CoachingRagRequest, CoachingRagResponse
from mc_contracts.internal_ai import InferenceRequest, InferenceResponse
from mc_foundation.objectstore import ObjectNotFoundError
from platform_service.auth.tenant_context import using_selected_tenant
from platform_service.db.base import SessionLocal
from platform_service.integrations.ai_runtime_client import AIRuntimeClient
from platform_service.services.coaching_rag_errors import CoachingRagError
from platform_service.services.coaching_rag_service import CoachingRagService

from eval.rag.answer_metrics import (
    artifact_category_slug,
    compute_e2e_metrics,
    compute_retrieval_metrics,
)
from eval.rag.citation_metrics import compute_citation_metrics
from eval.rag.context_metrics import compute_context_metrics
from eval.rag.corpus import CardCorpusDoc
from eval.rag.llm_judge import JudgeInput, LlmJudge, build_judge_context
from eval.rag.rag_dataset import RagGoldenRecord


@dataclass(frozen=True)
class LatencyMs:
    total: float
    generate: float | None = None
    embed: float | None = None


@dataclass(frozen=True)
class TokenUsage:
    input: int
    output: int


@dataclass(frozen=True)
class RagQueryResult:
    record_id: str
    category: str
    category_slug: str
    language: str
    query: str
    expected_answer: str
    expected_module_ids: list[str]
    expected_card_ids: list[str]
    answerable: str
    is_out_of_scope: bool
    answer: str
    model: str | None
    retrieved_module_ids: list[str]
    cited_module_ids: list[str]
    suggested_questions: list[str]
    cosine_distances: list[float]
    latency_ms: LatencyMs
    token_usage: TokenUsage
    error: str | None
    e2e_metrics: dict[str, float | bool | None]
    retrieval_metrics: dict[str, float | int | bool | None] | None
    context_metrics: dict[str, float] | None
    citation_metrics: dict[str, float | bool | None]
    judge_metrics: dict[str, float | str | None] | None
    generation_context: str


class EvalObjectStorage:
    """Minimal object storage stub for eval (attribution presign not required)."""

    bucket_name = "medtronics-storage"
    allowed_prefixes = frozenset({"uploads"})

    def object_name_from_reference(self, object_reference: str) -> str:
        clean = object_reference.strip().lstrip("/")
        if "/" in clean:
            _, _, rest = clean.partition("/")
            return rest or clean
        return clean

    async def presigned_get_url(
        self,
        *,
        object_name: str,
        expires_seconds: int,
        download_filename: str | None = None,
    ) -> object:
        raise ObjectNotFoundError(f"eval stub: object not found ({object_name})")


class InstrumentedAIRuntimeClient:
    """Wrap AIRuntimeClient to capture generate latency and token usage."""

    def __init__(self, client: AIRuntimeClient) -> None:
        self._client = client
        self.last_generate_latency_ms: float | None = None
        self.last_embed_latency_ms: float | None = None
        self.last_token_usage = TokenUsage(input=0, output=0)

    async def embed(self, texts: list[str], *, use_local: bool = False) -> list[list[float]]:
        started = time.perf_counter()
        result = await self._client.embed(texts, use_local=use_local)
        self.last_embed_latency_ms = (time.perf_counter() - started) * 1000.0
        return result

    async def generate(self, request: InferenceRequest, *, use_local: bool = False) -> InferenceResponse:
        started = time.perf_counter()
        response = await self._client.generate(request, use_local=use_local)
        self.last_generate_latency_ms = (time.perf_counter() - started) * 1000.0
        usage = response.token_usage
        self.last_token_usage = TokenUsage(input=usage.input, output=usage.output)
        return response

    async def aclose(self) -> None:
        await self._client.aclose()


def resolve_cited_card_ids_to_modules(
    cited_ids: list[str],
    cards_by_module: dict[UUID, list[CardCorpusDoc]],
) -> list[str]:
    """Map cited card UUIDs to parent module UUIDs for local card RAG eval."""
    card_to_module = {
        card.card_id: module_id for module_id, cards in cards_by_module.items() for card in cards
    }
    module_ids = set(cards_by_module.keys())
    resolved: list[str] = []
    seen: set[str] = set()
    for cited_id in cited_ids:
        try:
            cited_uuid = UUID(cited_id)
        except ValueError:
            continue
        if cited_uuid in card_to_module:
            module_id = str(card_to_module[cited_uuid])
        elif cited_uuid in module_ids:
            module_id = cited_id
        else:
            module_id = cited_id
        if module_id in seen:
            continue
        seen.add(module_id)
        resolved.append(module_id)
    return resolved


def _grounding_context_text(
    retrieved_module_ids: list[UUID],
    cited_module_ids: list[UUID],
    cards_by_module: dict[UUID, list[CardCorpusDoc]],
) -> str:
    module_ids: list[UUID] = []
    seen: set[UUID] = set()
    for module_id in [*retrieved_module_ids, *cited_module_ids]:
        if module_id in seen:
            continue
        seen.add(module_id)
        module_ids.append(module_id)
    return build_judge_context(module_ids, cards_by_module, max_chars=50_000)


class RagQueryRunner:
    """Run CoachingRagService queries for golden RAG records."""

    def __init__(
        self,
        *,
        tenant_id: int | None = None,
        base_url: str | None = None,
        token: str | None = None,
        cards_by_module: dict[UUID, list[CardCorpusDoc]] | None = None,
        llm_judge: LlmJudge | None = None,
        use_local: bool = False,
        local_card: bool = False,
    ) -> None:
        self._tenant_id = tenant_id
        self._use_local = use_local
        self._local_card = local_card
        base_client = AIRuntimeClient(base_url=base_url, token=token)
        self._ai = InstrumentedAIRuntimeClient(base_client)
        self._storage = EvalObjectStorage()
        self._owns_client = True
        self._cards_by_module = cards_by_module or {}
        self._llm_judge = llm_judge

    async def run_record(self, record: RagGoldenRecord, *, k: int) -> RagQueryResult:
        started = time.perf_counter()
        error: str | None = None
        answer = ""
        model: str | None = None
        retrieved_module_ids: list[str] = []
        cited_module_ids: list[str] = []
        suggested_questions: list[str] = []
        cosine_distances: list[float] = []
        generation_context = ""

        try:
            async with SessionLocal() as session:
                tenant_scope = (
                    using_selected_tenant(self._tenant_id) if self._tenant_id is not None else nullcontext()
                )
                with tenant_scope:
                    service = CoachingRagService(session, self._ai, self._storage)
                    if self._local_card:
                        local_body = CoachingLocalRagRequest(
                            question=record.query,
                            response_language=record.language,
                            include_generation_context=True,
                        )
                        response = await service.local_query(
                            local_body,
                            tenant_id=self._tenant_id,
                        )
                    else:
                        body = CoachingRagRequest(
                            question=record.query,
                            response_language=record.language,
                            include_generation_context=True,
                            use_local=self._use_local,
                        )
                        response = await service.query(
                            body,
                            tenant_id=self._tenant_id,
                        )
            (
                answer,
                model,
                retrieved_module_ids,
                cited_module_ids,
                suggested_questions,
                cosine_distances,
                generation_context,
            ) = _response_fields(response)
            if self._local_card and cited_module_ids:
                cited_module_ids = resolve_cited_card_ids_to_modules(
                    cited_module_ids,
                    self._cards_by_module,
                )
        except CoachingRagError as exc:
            error = exc.message

        total_ms = (time.perf_counter() - started) * 1000.0
        latency = LatencyMs(
            total=total_ms,
            generate=self._ai.last_generate_latency_ms,
            embed=self._ai.last_embed_latency_ms,
        )
        token_usage = self._ai.last_token_usage

        retrieved_uuids = [UUID(module_id) for module_id in retrieved_module_ids]
        cited_uuids = [UUID(module_id) for module_id in cited_module_ids]
        context_text = generation_context.strip() or _grounding_context_text(
            retrieved_uuids,
            cited_uuids,
            self._cards_by_module,
        )
        e2e_metrics = compute_e2e_metrics(
            record=record,
            answer=answer,
            cited_module_ids=cited_uuids,
            retrieved_module_ids=retrieved_uuids,
            error=error,
            context_text=context_text,
        )
        retrieval_metric_values = compute_retrieval_metrics(
            record=record,
            retrieved_module_ids=retrieved_uuids,
            cosine_distances=cosine_distances,
            k=k,
        )
        context_metric_values = compute_context_metrics(
            record=record,
            retrieved_module_ids=retrieved_uuids,
            cards_by_module=self._cards_by_module,
            k=k,
        )
        citation_metric_values = compute_citation_metrics(
            record=record,
            answer=answer,
            cited_module_ids=cited_uuids,
            retrieved_module_ids=retrieved_uuids,
        )

        judge_metric_values: dict[str, float | str | None] | None = None
        if self._llm_judge is not None and error is None:
            judge_input = JudgeInput(
                question=record.query,
                answer=answer,
                expected_answer=record.expected_answer,
                generation_context=context_text,
                answerable=record.answerable,
                is_out_of_scope=record.is_out_of_scope,
                category=record.category,
                language=record.language,
            )
            judge_scores = await self._llm_judge.score(judge_input)
            judge_metric_values = judge_scores.as_dict()

        return RagQueryResult(
            record_id=record.id,
            category=record.category,
            category_slug=artifact_category_slug(record),
            language=record.language,
            query=record.query,
            expected_answer=record.expected_answer,
            expected_module_ids=[str(module_id) for module_id in record.expected_module_ids],
            expected_card_ids=[str(card_id) for card_id in record.expected_card_ids],
            answerable=record.answerable,
            is_out_of_scope=record.is_out_of_scope,
            answer=answer,
            model=model,
            retrieved_module_ids=retrieved_module_ids,
            cited_module_ids=cited_module_ids,
            suggested_questions=suggested_questions,
            cosine_distances=cosine_distances,
            latency_ms=latency,
            token_usage=token_usage,
            error=error,
            e2e_metrics=e2e_metrics,
            retrieval_metrics=retrieval_metric_values,
            context_metrics=context_metric_values,
            citation_metrics=citation_metric_values,
            judge_metrics=judge_metric_values,
            generation_context=context_text,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._ai.aclose()


def _response_fields(
    response: CoachingRagResponse,
) -> tuple[str, str | None, list[str], list[str], list[str], list[float], str]:
    retrieved_module_ids = [str(hit.module_id) for hit in response.retrieved_modules]
    cosine_distances = [hit.cosine_distance for hit in response.retrieved_modules]
    cited_module_ids = [str(module_id) for module_id in response.cited_module_ids]
    return (
        response.answer,
        response.model,
        retrieved_module_ids,
        cited_module_ids,
        list(response.suggested_questions),
        cosine_distances,
        response.generation_context or "",
    )


def rag_result_to_artifact_dict(result: RagQueryResult) -> dict[str, object]:
    return {
        "id": result.record_id,
        "category": result.category,
        "category_slug": result.category_slug,
        "language": result.language,
        "query": result.query,
        "expected_answer": result.expected_answer,
        "expected_module_ids": result.expected_module_ids,
        "expected_card_ids": result.expected_card_ids,
        "answerable": result.answerable,
        "is_out_of_scope": result.is_out_of_scope,
        "answer": result.answer,
        "model": result.model,
        "retrieved_module_ids": result.retrieved_module_ids,
        "cited_module_ids": result.cited_module_ids,
        "suggested_questions": result.suggested_questions,
        "cosine_distances": result.cosine_distances,
        "latency_ms": {
            "total": result.latency_ms.total,
            "generate": result.latency_ms.generate,
            "embed": result.latency_ms.embed,
        },
        "token_usage": {
            "input": result.token_usage.input,
            "output": result.token_usage.output,
        },
        "error": result.error,
        "e2e_metrics": result.e2e_metrics,
        "retrieval_metrics": result.retrieval_metrics or {},
        "context_metrics": result.context_metrics or {},
        "citation_metrics": result.citation_metrics,
        "judge_metrics": result.judge_metrics or {},
        "generation_context": result.generation_context,
        "exact_match": result.e2e_metrics.get("exact_match"),
        "token_f1": result.e2e_metrics.get("token_f1"),
        "token_recall": result.e2e_metrics.get("token_recall"),
        "abstention_correct": result.e2e_metrics.get("abstention_correct"),
        "citation_accuracy": result.e2e_metrics.get("citation_accuracy"),
        "safety_pass": result.e2e_metrics.get("safety_pass"),
        "partial_answer_correct": result.e2e_metrics.get("partial_answer_correct"),
        "answer_grounding_overlap": result.e2e_metrics.get("answer_grounding_overlap"),
        "json_parse_success": result.e2e_metrics.get("json_parse_success"),
        "empty_answer": result.e2e_metrics.get("empty_answer"),
    }
