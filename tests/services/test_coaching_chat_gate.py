"""Unit tests for coaching chat cheap gate heuristics."""

from __future__ import annotations

import pytest
from platform_service.services.coaching_chat_gate import should_route_chat


@pytest.mark.parametrize(
    "question",
    [
        "Hello",
        "hello!",
        "Hey there",
        "Good morning",
        "Thanks",
        "Thank you",
        "Namaste",
        "হ্যালো",
        "ধন্যবাদ",
    ],
)
def test_phatic_messages_should_route(question: str) -> None:
    assert should_route_chat(question) is True


@pytest.mark.parametrize(
    "question",
    [
        "I want to kill myself",
        "thoughts of suicide tonight",
        "self-harm urges again",
        "আত্মহত্যা করতে চাই",
    ],
)
def test_crisis_cues_should_route(question: str) -> None:
    assert should_route_chat(question) is True


def test_short_non_clinical_should_route() -> None:
    assert should_route_chat("ok cool") is True
    assert should_route_chat("what's up?") is True


@pytest.mark.parametrize(
    "question",
    [
        "What is the referral threshold for BP 140/90?",
        "ANC visit steps for high-risk pregnancy",
        "How do I record diabetes dose in the app?",
        "Explain maternal danger signs during labour",
    ],
)
def test_clinical_questions_skip_gate(question: str) -> None:
    assert should_route_chat(question) is False


def test_short_clinical_still_skips_gate() -> None:
    assert should_route_chat("BP threshold?") is False
    assert should_route_chat("ANC protocol") is False


def test_hi_substring_in_this_does_not_false_positive() -> None:
    # Long enough and no phatic whole-token match → no gate.
    assert should_route_chat("What is the hypertension protocol for referral?") is False
