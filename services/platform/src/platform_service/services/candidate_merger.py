"""Batch candidate merge — collapse same-topic identify candidates.

Runs after every source in an ingest batch has finished per-chunk
module identification. Operates on candidate metadata plus short
cited-block excerpts. N-way groups are allowed, including same-document
chunk overlap.
"""

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from mc_contracts.enums import GenerationType
from mc_contracts.internal_ai import (
    GenerationConstraints,
    InferenceRequest,
    TraceContext,
)
from mc_foundation.locale import get_locale_metadata

from platform_service.deps import get_ai_client
from platform_service.integrations.ai_runtime_client import AIRuntimeClient
from platform_service.services.llm_response_resolver import resolve_parsed_json
from platform_service.services.prompt_registry import CANDIDATE_MERGER_TEMPLATE_ID
from platform_service.services.prompt_template_service import PromptTemplateService, prompt_spec_from_rendered
from platform_service.services.prompt_variables.candidate_merger_variables import (
    build_candidate_merger_variables,
)

logger = logging.getLogger(__name__)


def _annexure_terms_phrase(primary_locale: str) -> str:
    terms: list[str] = []
    for term in get_locale_metadata(primary_locale).annexure_terms:
        if term not in terms:
            terms.append(term)
    if not terms:
        return '"Annexure", "Appendix", or similar'
    quoted = ", ".join(f'"{term}"' for term in terms)
    return f"{quoted}, or similar"


@dataclass(frozen=True)
class MergeGroup:
    """One same-topic group. ``constituent_ids`` references input candidate IDs."""

    constituent_ids: list[uuid.UUID]
    merged_title: str
    merged_scope_summary: str
    pairing_rationale: str


@dataclass(frozen=True)
class CandidateMergerResult:
    """Outcome of one merge call.

    ``groups`` and ``unmerged_ids`` partition the input candidate list.
    """

    groups: list[MergeGroup]
    unmerged_ids: list[uuid.UUID]
    raw_response_text: str


class CandidateMergerError(Exception):
    """Raised when ai-runtime errors out or the LLM output is unusable."""


class CandidateMerger:
    """LLM merge of same-topic module candidates across a batch."""

    def __init__(self, client: AIRuntimeClient | None = None) -> None:
        self._client = client or get_ai_client()

    async def merge(
        self,
        candidates: list[dict[str, Any]],
        *,
        primary_locale: str,
        trace_context: TraceContext | None = None,
    ) -> CandidateMergerResult:
        """Run the candidate-merge call.

        ``candidates`` must each carry at minimum ``id`` and ``proposed_title``.
        When fewer than two candidates are present the LLM is skipped.
        """
        if len(candidates) < 2:
            return CandidateMergerResult(
                groups=[],
                unmerged_ids=[uuid.UUID(str(c["id"])) for c in candidates],
                raw_response_text="",
            )

        rendered = await PromptTemplateService().render(
            None,
            template_id=CANDIDATE_MERGER_TEMPLATE_ID,
            variant_key=None,
            variables=build_candidate_merger_variables(
                candidates=candidates,
                annexure_terms=_annexure_terms_phrase(primary_locale),
            ),
        )

        request = InferenceRequest(
            request_id=str(uuid.uuid4()),
            generation_type=GenerationType.CANDIDATE_MERGE,
            prompt=prompt_spec_from_rendered(rendered),
            constraints=GenerationConstraints(
                language="en",
                output_format="json",
            ),
            trace_context=trace_context or TraceContext(),
        )

        response = await self._client.generate(request)
        if response.error:
            raise CandidateMergerError(f"ai-runtime error: {response.error}")

        try:
            payload = resolve_parsed_json(response, fallback_text=response.raw_text or "{}")
        except json.JSONDecodeError as exc:
            raise CandidateMergerError(f"LLM output is not valid JSON: {exc}") from exc

        groups, unfused = _validate_and_partition(payload, candidates)
        logger.info(
            "Candidate merge: %d input candidates → %d groups (%d merged) + %d unmerged",
            len(candidates),
            len(groups),
            sum(len(g.constituent_ids) for g in groups),
            len(unfused),
        )
        return CandidateMergerResult(
            groups=groups,
            unmerged_ids=unfused,
            raw_response_text=response.raw_text,
        )


def _validate_and_partition(
    payload: Any,
    candidates: list[dict[str, Any]],
) -> tuple[list[MergeGroup], list[uuid.UUID]]:
    """Validate LLM output: known IDs, no overlap, groups size ≥ 2."""
    candidate_by_id: dict[uuid.UUID, dict[str, Any]] = {}
    for c in candidates:
        try:
            cid = uuid.UUID(str(c["id"]))
        except (KeyError, TypeError, ValueError):
            continue
        candidate_by_id[cid] = c

    groups: list[MergeGroup] = []
    used_ids: set[uuid.UUID] = set()

    raw_groups: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        raw_groups = list(payload.get("groups") or [])

    for raw in raw_groups:
        if not isinstance(raw, dict):
            continue
        raw_ids = raw.get("candidate_ids") or raw.get("constituent_ids") or []
        if not isinstance(raw_ids, list):
            continue
        valid_ids: list[uuid.UUID] = []
        for raw_id in raw_ids:
            try:
                cid = uuid.UUID(str(raw_id))
            except (TypeError, ValueError):
                logger.warning("Candidate merge: dropping invalid candidate_id %r", raw_id)
                continue
            if cid not in candidate_by_id:
                logger.warning("Candidate merge: dropping hallucinated candidate_id %s", cid)
                continue
            if cid in used_ids:
                logger.warning(
                    "Candidate merge: candidate %s appears in multiple groups; keeping first",
                    cid,
                )
                continue
            valid_ids.append(cid)
        if len(valid_ids) < 2:
            logger.warning(
                "Candidate merge: rejecting group with %d valid constituents (need ≥2)",
                len(valid_ids),
            )
            continue
        groups.append(
            MergeGroup(
                constituent_ids=valid_ids,
                merged_title=str(raw.get("merged_title") or "").strip()
                or str(candidate_by_id[valid_ids[0]].get("proposed_title") or ""),
                merged_scope_summary=str(raw.get("merged_scope_summary") or "").strip()
                or str(candidate_by_id[valid_ids[0]].get("scope_summary") or ""),
                pairing_rationale=str(raw.get("pairing_rationale") or "").strip(),
            )
        )
        used_ids.update(valid_ids)

    unfused = [cid for cid in candidate_by_id if cid not in used_ids]
    return groups, unfused
