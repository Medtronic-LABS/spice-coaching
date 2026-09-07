"""Unit tests for LLM-as-judge parsing and rubric selection."""

from __future__ import annotations

from uuid import UUID

from eval.rag.corpus import CardCorpusDoc
from eval.rag.llm_judge import (
    JudgeInput,
    build_judge_context,
    build_judge_human_message,
    judge_rubric_for_record,
    parse_judge_response,
)
from mc_contracts.enums import GenerationType
from mc_contracts.internal_ai import InferenceResponse, TokenUsage


def test_build_judge_context_respects_char_budget() -> None:
    module_id = UUID("11111111-1111-1111-1111-111111111111")
    cards_by_module = {
        module_id: [
            CardCorpusDoc(
                module_id=module_id,
                card_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
                card_index=0,
                card_family_id=None,
                primary_title="Card A",
                title_en=None,
                title_bn=None,
                text="x" * 500,
            )
        ]
    }
    context = build_judge_context([module_id], cards_by_module, max_chars=100)
    assert len(context) <= 120
    assert "MODULE" in context


def test_parse_judge_response_from_parsed_json() -> None:
    response = InferenceResponse(
        request_id="req-1",
        generation_type=GenerationType.RAG_EVAL_JUDGE,
        provider="google",
        model="test-model",
        max_tokens=512,
        temperature=0.0,
        raw_text="",
        parsed_json={
            "faithfulness": 0.9,
            "answer_relevance": 1.1,
            "groundedness": -0.2,
            "reference_correctness": 0.75,
            "abstention_appropriateness": None,
        },
        latency_ms=10,
        token_usage=TokenUsage(input=1, output=1),
        error=None,
    )
    scores = parse_judge_response(response)
    assert scores.faithfulness == 0.9
    assert scores.answer_relevance == 1.0
    assert scores.groundedness == 0.0
    assert scores.reference_correctness == 0.75
    assert scores.abstention_appropriateness is None
    assert scores.judge_error is None
    assert scores.judge_model == "test-model"


def test_parse_judge_response_handles_invalid_json() -> None:
    response = InferenceResponse(
        request_id="req-2",
        generation_type=GenerationType.RAG_EVAL_JUDGE,
        provider="google",
        model="test-model",
        max_tokens=512,
        temperature=0.0,
        raw_text="not json",
        parsed_json=None,
        latency_ms=10,
        token_usage=TokenUsage(input=1, output=1),
        error=None,
    )
    scores = parse_judge_response(response)
    assert scores.faithfulness is None
    assert scores.judge_error is not None


def test_judge_rubric_stratifies_by_record_type() -> None:
    out_of_scope = judge_rubric_for_record(answerable="no", is_out_of_scope=True, category="out-of-scope")
    partial = judge_rubric_for_record(answerable="partial", is_out_of_scope=False, category="ANC")
    adversarial = judge_rubric_for_record(
        answerable="yes",
        is_out_of_scope=False,
        category="edge / adversarial",
    )
    assert "out-of-scope" in out_of_scope
    assert "partial" in partial.casefold()
    assert "adversarial" in adversarial.casefold()


def test_build_judge_human_message_includes_reference_and_context() -> None:
    message = build_judge_human_message(
        JudgeInput(
            question="What is DOT?",
            answer="DOT means directly observed treatment.",
            expected_answer="Directly Observed Treatment short course.",
            generation_context="[[[ MODULE_BLOCK module_id=abc ]]]",
            answerable="yes",
            is_out_of_scope=False,
            category="TB",
            language="en",
        )
    )
    assert "EXPECTED_ANSWER" in message
    assert "GENERATION_CONTEXT" in message
    assert "Directly Observed Treatment" in message
