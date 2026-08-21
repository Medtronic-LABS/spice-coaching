"""Unit tests for coaching RAG JSON helpers (no DB / ai-runtime)."""

from __future__ import annotations

import pytest
from mc_foundation.problem import AppError
from platform_service.services.coaching_rag_service import CoachingRagService, parse_rag_json
from platform_service.services.llm_text_utils import format_grounded_rag_answer, strip_json_fence


def test_strip_json_fence_removes_markdown() -> None:
    raw = '```json\n{"answer": "ok", "cited_module_ids": []}\n```'
    stripped = strip_json_fence(raw)
    assert stripped.startswith("{")
    assert "answer" in stripped


def test_parse_rag_json_accepts_pre_parsed_dict() -> None:
    out = parse_rag_json("ignored", {"answer": "x", "cited_module_ids": []})
    assert out["answer"] == "x"


def test_parse_rag_json_parses_raw_string() -> None:
    out = parse_rag_json('{"answer": "y", "cited_module_ids": []}', None)
    assert out["answer"] == "y"


def test_parse_rag_json_raises_on_garbage() -> None:
    with pytest.raises(AppError) as exc:
        parse_rag_json("not json {{{", None)
    assert exc.value.status == 502


class TestFormatGroundedRagAnswer:
    def test_dense_english_paragraph_becomes_bullets(self) -> None:
        raw = (
            "Check the mother for danger signs. "
            "Refer urgently if bleeding continues. "
            "Reassure the family while arranging transport."
        )
        out = format_grounded_rag_answer(raw)
        assert out == (
            "• Check the mother for danger signs.\n"
            "• Refer urgently if bleeding continues.\n"
            "• Reassure the family while arranging transport."
        )

    def test_bangla_danda_splits(self) -> None:
        raw = "প্রথম পয়েন্ট। দ্বিতীয় পয়েন্ট। তৃতীয় পয়েন্ট।"
        out = format_grounded_rag_answer(raw)
        assert out == "• প্রথম পয়েন্ট।\n• দ্বিতীয় পয়েন্ট।\n• তৃতীয় পয়েন্ট।"

    def test_short_answer_unchanged(self) -> None:
        raw = "Training materials do not cover this. Ask a supervisor."
        assert format_grounded_rag_answer(raw) == raw

    def test_already_bulleted_unchanged(self) -> None:
        raw = "• First point.\n• Second point.\n• Third point."
        assert format_grounded_rag_answer(raw) == raw

    def test_already_newlined_unchanged(self) -> None:
        raw = "First point.\nSecond point.\nThird point."
        assert format_grounded_rag_answer(raw) == raw

    def test_markdown_list_prefix_unchanged(self) -> None:
        raw = "- First point is important. Second point follows carefully. Third point closes the guidance."
        assert format_grounded_rag_answer(raw) == raw

    def test_decimal_not_split(self) -> None:
        raw = (
            "Give 2.5 mg if prescribed. "
            "Monitor for side effects carefully. "
            "Document the dose in the register."
        )
        out = format_grounded_rag_answer(raw)
        assert "2.5 mg" in out
        assert out.startswith("• ")
        assert out.count("\n") == 2

    def test_abbreviation_not_split(self) -> None:
        raw = "Ask Dr. Rahman to review the case. Use ORS for mild dehydration. Follow up the next day."
        out = format_grounded_rag_answer(raw)
        assert "Dr. Rahman" in out.split("\n")[0]
        assert out.count("\n") == 2

    def test_empty_and_whitespace(self) -> None:
        assert format_grounded_rag_answer("") == ""
        assert format_grounded_rag_answer("   ") == ""


class TestParseSuggestedQuestions:
    def test_valid_list(self) -> None:
        out = CoachingRagService._parse_suggested_questions(["  First?  ", "Second?", "Third?"])
        assert out == ["First?", "Second?", "Third?"]

    def test_strips_and_drops_empty(self) -> None:
        out = CoachingRagService._parse_suggested_questions(["  ok  ", "", "   ", 42, None])
        assert out == ["ok"]

    def test_dedupes_case_insensitive(self) -> None:
        out = CoachingRagService._parse_suggested_questions(["What?", "what?", "WHAT?"])
        assert out == ["What?"]

    def test_caps_at_max_count(self) -> None:
        raw = [f"Q{i}?" for i in range(10)]
        out = CoachingRagService._parse_suggested_questions(raw, max_count=5)
        assert len(out) == 5
        assert out == [f"Q{i}?" for i in range(5)]

    def test_non_list_returns_empty(self) -> None:
        assert CoachingRagService._parse_suggested_questions(None) == []
        assert CoachingRagService._parse_suggested_questions("not a list") == []
        assert CoachingRagService._parse_suggested_questions({}) == []
