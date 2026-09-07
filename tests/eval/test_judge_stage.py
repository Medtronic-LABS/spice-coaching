"""Unit tests for offline judge stage helpers."""

from __future__ import annotations

from eval.rag.judge_stage import judge_input_from_artifact, merge_judge_summary


def test_judge_input_from_artifact_maps_rag_fields() -> None:
    judge_input = judge_input_from_artifact(
        {
            "id": "rec-1",
            "query": "What is DOT?",
            "answer": "Directly observed treatment.",
            "expected_answer": "DOT is directly observed treatment.",
            "generation_context": "[[[ MODULE_BLOCK ]]]",
            "answerable": "yes",
            "is_out_of_scope": False,
            "category": "TB",
            "language": "en",
        }
    )
    assert judge_input is not None
    assert judge_input.question == "What is DOT?"
    assert judge_input.generation_context.startswith("[[[")


def test_judge_input_from_bm25_generation_artifact() -> None:
    judge_input = judge_input_from_artifact(
        {
            "id": "rec-2",
            "question": "How to collect sputum?",
            "answer": "Collect early morning sputum.",
            "expected_answer": "Collect two samples.",
            "generation_context": "context blob",
            "answerable": "partial",
            "is_out_of_scope": False,
            "category": "TB",
            "question_lang": "bn",
        }
    )
    assert judge_input is not None
    assert judge_input.language == "bn"
    assert judge_input.answerable == "partial"


def test_merge_judge_summary_updates_generation_report() -> None:
    report = {
        "retrieval_method": "bm25",
        "artifacts": [{"judge_metrics": {"faithfulness": 0.8}}],
    }
    judged = [{"judge_metrics": {"faithfulness": 0.8, "reference_correctness": 0.7}}]
    merged = merge_judge_summary(report, judged)
    assert "judge_summary" in merged
    assert float(merged["judge_summary"]["faithfulness"]) == 0.8  # type: ignore[index]
