"""Cheap heuristic gate before coaching chat LLM routing."""

from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")

# Short utterances without clinical tokens may still be chit-chat.
_SHORT_UTTERANCE_MAX_CHARS = 48

_CRISIS_CUES: frozenset[str] = frozenset(
    {
        "suicide",
        "suicidal",
        "self-harm",
        "self harm",
        "selfharm",
        "kill myself",
        "killing myself",
        "end my life",
        "want to die",
        "hurt myself",
        "emergency now",
        "আত্মহত্যা",
        "আমি মরতে চাই",
    }
)

_PHATIC_CUES: frozenset[str] = frozenset(
    {
        "hi",
        "hii",
        "hiii",
        "hello",
        "hello!",
        "hey",
        "hey!",
        "hiya",
        "yo",
        "thanks",
        "thank you",
        "thankyou",
        "thx",
        "ty",
        "bye",
        "goodbye",
        "good bye",
        "good morning",
        "good afternoon",
        "good evening",
        "good night",
        "how are you",
        "how's it going",
        "whats up",
        "what's up",
        "namaste",
        "hola",
        "ok",
        "okay",
        "ok thanks",
        "okay thanks",
        "হাই",
        "হ্যালো",
        "নমস্কার",
        "শুভ সকাল",
        "শুভ সন্ধ্যা",
        "ধন্যবাদ",
        "বিদায়",
        "কেমন আছো",
        "কেমন আছেন",
    }
)

_CLINICAL_KEYWORDS: frozenset[str] = frozenset(
    {
        "bp",
        "blood pressure",
        "hypertension",
        "diabetes",
        "glucose",
        "insulin",
        "dose",
        "dosage",
        "tablet",
        "referral",
        "refer",
        "anc",
        "pnc",
        "pregnancy",
        "pregnant",
        "eclampsia",
        "pre-eclampsia",
        "preeclampsia",
        "protocol",
        "symptom",
        "symptoms",
        "danger sign",
        "danger signs",
        "module",
        "quiz",
        "training",
        "counselling",
        "counseling",
        "medication",
        "medicine",
        "mmhg",
        "fever",
        "bleeding",
        "labor",
        "labour",
        "newborn",
        "maternal",
        "চিকিত্সা",
        "ডোজ",
        "রেফারেল",
        "গর্ভাবস্থা",
        "ডায়াবেটিস",
    }
)


def _normalize(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.strip()).casefold()


def _contains_any(normalized: str, cues: frozenset[str]) -> bool:
    for cue in cues:
        if " " in cue or any(ord(ch) > 127 for ch in cue):
            if cue in normalized:
                return True
            continue
        # Word-ish match for simple ASCII tokens to avoid "hi" in "this".
        if re.search(rf"(?<!\w){re.escape(cue)}(?!\w)", normalized):
            return True
    return False


def should_route_chat(question: str) -> bool:
    """Return True when the message should hit the LLM chat router before RAG."""
    normalized = _normalize(question)
    if not normalized:
        return False
    if _contains_any(normalized, _CRISIS_CUES):
        return True
    if _contains_any(normalized, _PHATIC_CUES):
        return True
    if len(normalized) <= _SHORT_UTTERANCE_MAX_CHARS and not _contains_any(normalized, _CLINICAL_KEYWORDS):
        return True
    return False
