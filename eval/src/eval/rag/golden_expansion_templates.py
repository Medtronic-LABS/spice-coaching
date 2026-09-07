"""Deterministic template fallback for golden dataset expansion."""

from __future__ import annotations

import re
from itertools import cycle

from mc_foundation.locale import localized_primary_text
from platform_service.services.card_body_text import card_body_plain_text

from eval.rag.corpus import card_text_for_search

LINGUISTIC_VARIATIONS = [
    "Standard Written Bengali",
    "Colloquial Spoken Bengali",
    "Roman Transliteration",
    "Banglish",
]

QUERY_ROTATION = [
    "Factual",
    "Situational",
    "Procedural",
    "Referral Decision",
    "Factual",
    "Procedural",
    "Cross-card Synthesis",
    "Counseling",
    "Drug / Dosage",
    "Situational",
]

CHW_PATTERNS = {
    "Factual": "Symptom Identification",
    "Situational": "Problem Identification & Escalation",
    "Procedural": "Treatment Protocol",
    "Referral Decision": "Referral & Escalation",
    "Cross-card Synthesis": "Cross-module Integration",
    "Counseling": "Patient Education",
    "Drug / Dosage": "Treatment Protocol",
}

MAKERS = {}


def _plain_card_text(card: dict[str, object], field: str, *, locale: str = "bn") -> str:
    value = card.get(f"{field}_localized") or card.get(field)
    if isinstance(value, dict):
        text = value.get(locale) or localized_primary_text(value, locale)
        return str(text or "").strip()
    return str(value or "").strip()


def _card_body(card: dict[str, object], *, locale: str = "bn") -> str:
    value = card.get("body_localized") or card.get("body")
    if isinstance(value, dict):
        raw = value.get(locale) or localized_primary_text(value, locale)
        return card_body_plain_text(raw)
    return card_body_plain_text(value)


def _first_sentences(text: str, count: int = 2, max_len: int = 400) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return ""
    parts = re.split(r"(?<=[।.!?])\s+", cleaned)
    result = " ".join(parts[:count]).strip()
    if len(result) > max_len:
        return result[: max_len - 3].rstrip() + "..."
    return result


def _make_factual(
    record_id: str, module_id: str, card: dict[str, object], linguistic: str
) -> dict[str, object]:
    title_bn = _plain_card_text(card, "title", locale="bn") or "এই বিষয়"
    body_bn = _card_body(card, locale="bn") or card_text_for_search(card)
    answer_bn = _first_sentences(body_bn) or title_bn
    title_en = _plain_card_text(card, "title", locale="en") or title_bn
    body_en = _card_body(card, locale="en") or answer_bn
    answer_en = _first_sentences(body_en) or title_en
    return {
        "id": record_id,
        "question_en": f"What should a health worker know about {title_en}?",
        "expected_answer_en": answer_en,
        "question_bn": f"একজন স্বাস্থ্যকর্মী {title_bn} সম্পর্কে কী জানতে হবে?",
        "expected_answer_bn": answer_bn,
        "source_card_id": [str(card["id"])],
        "query_type": "Factual",
        "linguistic_variation": linguistic,
        "chw_pattern": CHW_PATTERNS["Factual"],
        "answerable": "yes",
        "confidence": "high",
        "module_id": [module_id],
    }


def _make_situational(
    record_id: str, module_id: str, card: dict[str, object], linguistic: str
) -> dict[str, object]:
    title_bn = _plain_card_text(card, "title", locale="bn")
    body_bn = _card_body(card, locale="bn") or card_text_for_search(card)
    answer_bn = _first_sentences(body_bn, count=3)
    title_en = _plain_card_text(card, "title", locale="en") or title_bn
    body_en = _card_body(card, locale="en") or answer_bn
    answer_en = _first_sentences(body_en, count=3)
    return {
        "id": record_id,
        "question_en": f"During a home visit I encounter a case related to {title_en}. As an SK, what should I do?",
        "expected_answer_en": answer_en,
        "question_bn": f"বাড়ি ভিজিটে {title_bn} সম্পর্কিত একটি পরিস্থিতি দেখলাম। SK হিসেবে আমার করণীয় কী?",
        "expected_answer_bn": answer_bn,
        "source_card_id": [str(card["id"])],
        "query_type": "Situational",
        "linguistic_variation": linguistic,
        "chw_pattern": CHW_PATTERNS["Situational"],
        "answerable": "yes",
        "confidence": "high",
        "module_id": [module_id],
    }


def _make_procedural(
    record_id: str, module_id: str, card: dict[str, object], linguistic: str
) -> dict[str, object]:
    title_bn = _plain_card_text(card, "title", locale="bn")
    body_bn = _card_body(card, locale="bn") or card_text_for_search(card)
    answer_bn = _first_sentences(body_bn, count=3)
    title_en = _plain_card_text(card, "title", locale="en") or title_bn
    body_en = _card_body(card, locale="en") or answer_bn
    answer_en = _first_sentences(body_en, count=3)
    return {
        "id": record_id,
        "question_en": f"What is the procedure for {title_en}?",
        "expected_answer_en": answer_en,
        "question_bn": f"{title_bn} এর পদ্ধতি কী?",
        "expected_answer_bn": answer_bn,
        "source_card_id": [str(card["id"])],
        "query_type": "Procedural",
        "linguistic_variation": linguistic,
        "chw_pattern": CHW_PATTERNS["Procedural"],
        "answerable": "yes",
        "confidence": "high",
        "module_id": [module_id],
    }


def _make_referral(
    record_id: str, module_id: str, card: dict[str, object], linguistic: str
) -> dict[str, object]:
    title_bn = _plain_card_text(card, "title", locale="bn")
    body_bn = _card_body(card, locale="bn") or card_text_for_search(card)
    answer_bn = _first_sentences(body_bn, count=2)
    title_en = _plain_card_text(card, "title", locale="en") or title_bn
    body_en = _card_body(card, locale="en") or answer_bn
    answer_en = _first_sentences(body_en, count=2)
    return {
        "id": record_id,
        "question_en": f"When should I refer a patient related to {title_en}?",
        "expected_answer_en": answer_en,
        "question_bn": f"{title_bn} সম্পর্কিত রোগীকে কখন রেফার করতে হবে?",
        "expected_answer_bn": answer_bn,
        "source_card_id": [str(card["id"])],
        "query_type": "Referral Decision",
        "linguistic_variation": linguistic,
        "chw_pattern": CHW_PATTERNS["Referral Decision"],
        "answerable": "yes",
        "confidence": "high",
        "module_id": [module_id],
    }


def _make_cross_card(
    record_id: str,
    module_id: str,
    cards: list[dict[str, object]],
    linguistic: str,
) -> dict[str, object] | None:
    if len(cards) < 2:
        return None
    first, second = cards[0], cards[1]
    title_bn = _plain_card_text(first, "title", locale="bn")
    body_bn = _first_sentences(_card_body(first, locale="bn"), 1)
    body2_bn = _first_sentences(_card_body(second, locale="bn"), 1)
    answer_bn = f"{body_bn} {body2_bn}".strip()
    title_en = _plain_card_text(first, "title", locale="en") or title_bn
    body_en = _first_sentences(_card_body(first, locale="en"), 1)
    body2_en = _first_sentences(_card_body(second, locale="en"), 1)
    answer_en = f"{body_en} {body2_en}".strip() or answer_bn
    return {
        "id": record_id,
        "question_en": f"How do {title_en} and related care steps work together in practice?",
        "expected_answer_en": answer_en,
        "question_bn": f"{title_bn} এবং সম্পর্কিত যত্নের ধাপগুলো একসাথে কীভাবে প্রয়োগ করব?",
        "expected_answer_bn": answer_bn,
        "source_card_id": [str(first["id"]), str(second["id"])],
        "query_type": "Cross-card Synthesis",
        "linguistic_variation": linguistic,
        "chw_pattern": CHW_PATTERNS["Cross-card Synthesis"],
        "answerable": "yes",
        "confidence": "high",
        "module_id": [module_id],
    }


MAKERS.update(
    {
        "Factual": _make_factual,
        "Situational": _make_situational,
        "Procedural": _make_procedural,
        "Referral Decision": _make_referral,
        "Counseling": _make_situational,
        "Drug / Dosage": _make_procedural,
    }
)


def generate_template_records_for_module(
    *,
    module_id: str,
    cards: list[dict[str, object]],
    needed: int,
    start_id: int,
    linguistic_cycle: cycle[str],
    query_cycle: cycle[str],
) -> tuple[list[dict[str, object]], int]:
    """Generate template-based records for one module. Returns (records, next_id)."""
    records: list[dict[str, object]] = []
    next_id = start_id
    generated = 0
    card_index = 0

    while generated < needed and card_index < len(cards) * 2:
        query_type = next(query_cycle)
        linguistic = next(linguistic_cycle)
        card = cards[card_index % len(cards)]
        card_index += 1

        if query_type == "Cross-card Synthesis":
            record = _make_cross_card(f"Q{next_id:03d}", module_id, cards, linguistic)
        else:
            maker = MAKERS.get(query_type, _make_factual)
            record = maker(f"Q{next_id:03d}", module_id, card, linguistic)

        if record is None:
            continue

        records.append(record)
        next_id += 1
        generated += 1

    return records, next_id


def target_records_for_module(card_count: int) -> int:
    if card_count <= 3:
        return 4
    if card_count <= 6:
        return 6
    if card_count <= 8:
        return 8
    return min(12, card_count + 2)
