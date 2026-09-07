"""Batch candidate-merger parser and skip-LLM tests."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from mc_contracts.enums import GenerationType
from mc_contracts.internal_ai import InferenceRequest, InferenceResponse, TokenUsage
from platform_service.services.candidate_merge_runner import _truncate_excerpt
from platform_service.services.candidate_merger import CandidateMerger, CandidateMergerError

pytestmark = pytest.mark.usefixtures("mock_prompt_templates")


def _candidate(
    *,
    cid: UUID | None = None,
    source_doc_id: UUID | None = None,
    title: str = "Sample",
    scope: str = "Sample scope.",
) -> dict[str, Any]:
    return {
        "id": cid or uuid4(),
        "source_document_id": source_doc_id or uuid4(),
        "proposed_title": title,
        "scope_summary": scope,
    }


def _mock_response(
    parsed_json: Any = None, *, raw_text: str = "", error: str | None = None
) -> InferenceResponse:
    return InferenceResponse(
        request_id="r-1",
        generation_type=GenerationType.CANDIDATE_MERGE,
        provider="google",
        model="gemini-2.5-flash",
        max_tokens=8192,
        temperature=0.2,
        raw_text=raw_text,
        parsed_json=parsed_json,
        latency_ms=200,
        token_usage=TokenUsage(input=300, output=200),
        error=error,
    )


def _group_payload(*cands: dict[str, Any], title: str = "Merged") -> dict[str, Any]:
    return {
        "groups": [
            {
                "candidate_ids": [str(c["id"]) for c in cands],
                "merged_title": title,
                "merged_scope_summary": "Merged scope.",
                "pairing_rationale": "Same topic.",
            }
        ]
    }


class TestSkipLlm:
    @pytest.mark.asyncio
    async def test_empty_input_skips_llm(self) -> None:
        client = MagicMock()
        client.generate = AsyncMock()
        merger = CandidateMerger(client=client)
        result = await merger.merge([], primary_locale="en")
        assert result.groups == []
        assert result.unmerged_ids == []
        client.generate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_single_candidate_skips_llm(self) -> None:
        client = MagicMock()
        client.generate = AsyncMock()
        merger = CandidateMerger(client=client)
        c = _candidate()
        result = await merger.merge([c], primary_locale="en")
        assert result.groups == []
        assert result.unmerged_ids == [UUID(str(c["id"]))]
        client.generate.assert_not_awaited()


class TestMergeHappyPath:
    @pytest.mark.asyncio
    async def test_n_way_group_and_unmerged_leftover(self) -> None:
        same_doc = uuid4()
        c1 = _candidate(source_doc_id=same_doc, title="ANC chunk 1")
        c2 = _candidate(source_doc_id=same_doc, title="ANC chunk 2")
        c3 = _candidate(source_doc_id=same_doc, title="ANC chunk 3")
        solo = _candidate(title="Diabetes")
        client = MagicMock()
        client.generate = AsyncMock(
            return_value=_mock_response(
                {
                    "groups": [
                        {
                            "candidate_ids": [str(c1["id"]), str(c2["id"]), str(c3["id"])],
                            "merged_title": "ANC counselling",
                            "merged_scope_summary": "Unified ANC.",
                            "pairing_rationale": "Same topic across chunks.",
                        }
                    ]
                }
            )
        )
        merger = CandidateMerger(client=client)
        result = await merger.merge([c1, c2, c3, solo], primary_locale="en")
        assert len(result.groups) == 1
        assert set(result.groups[0].constituent_ids) == {
            UUID(str(c1["id"])),
            UUID(str(c2["id"])),
            UUID(str(c3["id"])),
        }
        assert result.unmerged_ids == [UUID(str(solo["id"]))]

    @pytest.mark.asyncio
    async def test_same_document_group_allowed(self) -> None:
        same_doc = uuid4()
        c1 = _candidate(source_doc_id=same_doc)
        c2 = _candidate(source_doc_id=same_doc)
        client = MagicMock()
        client.generate = AsyncMock(return_value=_mock_response(_group_payload(c1, c2)))
        merger = CandidateMerger(client=client)
        result = await merger.merge([c1, c2], primary_locale="en")
        assert len(result.groups) == 1
        assert set(result.groups[0].constituent_ids) == {
            UUID(str(c1["id"])),
            UUID(str(c2["id"])),
        }

    @pytest.mark.asyncio
    async def test_inference_request_uses_candidate_merge_type(self) -> None:
        client = MagicMock()
        client.generate = AsyncMock(return_value=_mock_response({"groups": []}))
        merger = CandidateMerger(client=client)
        await merger.merge([_candidate(), _candidate()], primary_locale="en")
        sent: InferenceRequest = client.generate.call_args.args[0]
        assert sent.generation_type == GenerationType.CANDIDATE_MERGE
        assert sent.constraints.output_format == "json"


class TestMergeValidation:
    @pytest.mark.asyncio
    async def test_hallucinated_id_dropped(self) -> None:
        c1, c2 = _candidate(), _candidate()
        client = MagicMock()
        client.generate = AsyncMock(
            return_value=_mock_response(
                {
                    "groups": [
                        {
                            "candidate_ids": [str(c1["id"]), str(c2["id"]), str(uuid4())],
                            "merged_title": "T",
                            "merged_scope_summary": "S",
                            "pairing_rationale": "R",
                        }
                    ]
                }
            )
        )
        merger = CandidateMerger(client=client)
        result = await merger.merge([c1, c2], primary_locale="en")
        assert len(result.groups) == 1
        assert set(result.groups[0].constituent_ids) == {
            UUID(str(c1["id"])),
            UUID(str(c2["id"])),
        }

    @pytest.mark.asyncio
    async def test_group_below_two_valid_ids_rejected(self) -> None:
        c1, c2 = _candidate(), _candidate()
        client = MagicMock()
        client.generate = AsyncMock(
            return_value=_mock_response(
                {
                    "groups": [
                        {
                            "candidate_ids": [str(c1["id"]), str(uuid4())],
                            "merged_title": "T",
                            "merged_scope_summary": "S",
                            "pairing_rationale": "R",
                        }
                    ]
                }
            )
        )
        merger = CandidateMerger(client=client)
        result = await merger.merge([c1, c2], primary_locale="en")
        assert result.groups == []
        assert set(result.unmerged_ids) == {UUID(str(c1["id"])), UUID(str(c2["id"]))}

    @pytest.mark.asyncio
    async def test_overlapping_groups_first_wins(self) -> None:
        c1, c2, c3 = _candidate(), _candidate(), _candidate()
        client = MagicMock()
        client.generate = AsyncMock(
            return_value=_mock_response(
                {
                    "groups": [
                        {
                            "candidate_ids": [str(c1["id"]), str(c2["id"])],
                            "merged_title": "G1",
                            "merged_scope_summary": "S1",
                            "pairing_rationale": "R1",
                        },
                        {
                            "candidate_ids": [str(c1["id"]), str(c3["id"])],
                            "merged_title": "G2",
                            "merged_scope_summary": "S2",
                            "pairing_rationale": "R2",
                        },
                    ]
                }
            )
        )
        merger = CandidateMerger(client=client)
        result = await merger.merge([c1, c2, c3], primary_locale="en")
        assert len(result.groups) == 1
        assert result.groups[0].merged_title == "G1"
        assert result.unmerged_ids == [UUID(str(c3["id"]))]

    @pytest.mark.asyncio
    async def test_empty_groups_returns_all_unmerged(self) -> None:
        client = MagicMock()
        client.generate = AsyncMock(return_value=_mock_response({"groups": []}))
        merger = CandidateMerger(client=client)
        c1, c2 = _candidate(), _candidate()
        result = await merger.merge([c1, c2], primary_locale="en")
        assert result.groups == []
        assert set(result.unmerged_ids) == {UUID(str(c1["id"])), UUID(str(c2["id"]))}


class TestMergerFailures:
    @pytest.mark.asyncio
    async def test_ai_runtime_error_raises(self) -> None:
        client = MagicMock()
        client.generate = AsyncMock(return_value=_mock_response(error="429 RESOURCE_EXHAUSTED"))
        merger = CandidateMerger(client=client)
        with pytest.raises(CandidateMergerError, match="429"):
            await merger.merge([_candidate(), _candidate()], primary_locale="en")

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self) -> None:
        client = MagicMock()
        client.generate = AsyncMock(return_value=_mock_response(None, raw_text="not json {{"))
        merger = CandidateMerger(client=client)
        with pytest.raises(CandidateMergerError, match="not valid JSON"):
            await merger.merge([_candidate(), _candidate()], primary_locale="en")


class TestPartitionInvariant:
    @pytest.mark.asyncio
    async def test_every_input_id_appears_exactly_once(self) -> None:
        cands = [_candidate(title=t) for t in ("A", "B", "C", "D")]
        client = MagicMock()
        client.generate = AsyncMock(
            return_value=_mock_response(_group_payload(cands[0], cands[2], title="AC"))
        )
        merger = CandidateMerger(client=client)
        result = await merger.merge(cands, primary_locale="en")
        all_input = {UUID(str(c["id"])) for c in cands}
        all_output: set[UUID] = set()
        for g in result.groups:
            all_output.update(g.constituent_ids)
        all_output.update(result.unmerged_ids)
        assert all_output == all_input
        assert sum(len(g.constituent_ids) for g in result.groups) + len(result.unmerged_ids) == len(cands)


class TestExcerptTruncation:
    def test_short_text_unchanged(self) -> None:
        assert _truncate_excerpt("hello", 400) == "hello"

    def test_empty_or_zero_cap(self) -> None:
        assert _truncate_excerpt("hello", 0) == ""
        assert _truncate_excerpt("", 400) == ""
