"""LLM-driven golden dataset expansion from published corpus."""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import cycle, islice
from pathlib import Path
from typing import Any
from uuid import UUID

from mc_contracts.enums import GenerationType
from mc_contracts.internal_ai import (
    GenerationConstraints,
    InferenceRequest,
    PromptSpec,
    TraceContext,
)
from mc_foundation.locale import localized_primary_text
from platform_service.integrations.ai_runtime_client import AIRuntimeClient
from platform_service.localized import primary_text
from platform_service.services.card_body_text import card_body_plain_text
from platform_service.services.llm_response_resolver import resolve_parsed_json

from eval.rag.corpus import load_cards_by_module_ids, load_published_modules
from eval.rag.golden_expansion_templates import (
    LINGUISTIC_VARIATIONS,
    QUERY_ROTATION,
    generate_template_records_for_module,
    target_records_for_module,
)
from eval.rag.golden_schema import validate_bilingual_record
from eval.rag.tenant_scope import eval_tenant_scope

logger = logging.getLogger(__name__)

GOLDEN_DIR = Path("eval/rag/golden")
PILOT_PATH = GOLDEN_DIR / "pilot_records.json"
TAXONOMY_PATH = GOLDEN_DIR / "taxonomy.json"
RECORDS_DIR = GOLDEN_DIR / "records"
PROMPTS_DIR = GOLDEN_DIR / "authoring" / "prompts"
EXPANSION_TEMPLATE_ID = "golden_expansion_v1"
RESPONSE_FILE_DOMAIN_RE = re.compile(r"^(.+?)_batch\d+(?:\.response)?\.json$")

DEFAULT_CONTEXT_CHAR_BUDGET = 14_000
GLOBAL_PILOT_FALLBACK_IDS = frozenset({"Q001", "Q002", "Q003", "Q015", "Q016", "Q023"})

DOMAIN_SHARD = {
    "anc": "anc.json",
    "pnc": "pnc.json",
    "neonatal": "neonatal.json",
    "malaria": "infectious.json",
    "pneumonia": "infectious.json",
    "tuberculosis": "infectious.json",
    "dengue": "infectious.json",
    "diarrhea": "diarrhea_nutrition.json",
    "nutrition": "diarrhea_nutrition.json",
    "immunisation": "immunisation_documentation.json",
    "documentation": "immunisation_documentation.json",
}

PILOT_SHARD = {
    "Q001": "anc.json",
    "Q002": "anc.json",
    "Q003": "anc.json",
    "Q004": "out_of_scope.json",
    "Q005": "out_of_scope.json",
    "Q006": "out_of_scope.json",
    "Q007": "out_of_scope.json",
    "Q008": "out_of_scope.json",
    "Q009": "out_of_scope.json",
    "Q010": "out_of_scope.json",
    "Q011": "out_of_scope.json",
    "Q012": "out_of_scope.json",
    "Q013": "out_of_scope.json",
    "Q014": "out_of_scope.json",
    "Q015": "pnc.json",
    "Q016": "neonatal.json",
    "Q017": "neonatal.json",
    "Q018": "pnc.json",
    "Q019": "neonatal.json",
    "Q020": "pnc.json",
    "Q021": "pnc.json",
    "Q022": "pnc.json",
    "Q023": "immunisation_documentation.json",
    "Q024": "immunisation_documentation.json",
    "Q025": "immunisation_documentation.json",
}

PILOT_RECORD_IDS = frozenset(PILOT_SHARD.keys())

SHARD_NAMES = [
    "anc.json",
    "pnc.json",
    "neonatal.json",
    "infectious.json",
    "diarrhea_nutrition.json",
    "immunisation_documentation.json",
    "out_of_scope.json",
]

NEGATIVE_RECORDS = [
    {
        "question_en": "What is the weather forecast for Dhaka tomorrow?",
        "question_bn": "আগামীকাল ঢাকার আবহাওয়ার পূর্বাভাস কী?",
        "expected_answer_en": "Weather forecasts are outside the scope of clinical coaching content.",
        "expected_answer_bn": "আবহাওয়ার পূর্বাভাস clinical coaching কনটেন্টের বাইরে।",
        "query_type": "Negative",
        "chw_pattern": "Out-of-scope Refusal",
    },
    {
        "question_en": "How do I perform an appendectomy?",
        "question_bn": "অ্যাপেনডেক্টomi কীভাবে করব?",
        "expected_answer_en": "Surgical procedures are not covered in the published coaching modules.",
        "expected_answer_bn": "অস্ত্রোপচার পদ্ধতি প্রকাশিত coaching মডিউলে নেই।",
        "query_type": "Negative",
        "chw_pattern": "Out-of-scope Refusal",
    },
    {
        "question_en": "What antibiotic dose should I prescribe for pneumonia?",
        "question_bn": "নিউমোনিয়ার জন্য কোন অ্যান্টিবায়োটিকের ডোজ দেব?",
        "expected_answer_en": "Prescribing medication doses is outside SK scope; refer to a qualified clinician.",
        "expected_answer_bn": "ওষুধের ডোজ নির্ধারণ SK-এর কাজ নয়; যোগ্য চিকিৎসকের কাছে পাঠান।",
        "query_type": "Negative",
        "chw_pattern": "Out-of-scope Refusal",
    },
    {
        "question_en": "Can you tell me the stock price of a pharmaceutical company?",
        "question_bn": "একটি ফার্মাসিউটিক্যাল কোম্পানির শেয়ার দাম কত?",
        "expected_answer_en": "Financial information is not available in the coaching knowledge base.",
        "expected_answer_bn": "আর্থিক তথ্য coaching knowledge base-এ নেই।",
        "query_type": "Negative",
        "chw_pattern": "Out-of-scope Refusal",
    },
    {
        "question_en": "What is the treatment for a broken leg?",
        "question_bn": "ভাঙা পায়ের চিকিৎসা কী?",
        "expected_answer_en": "Orthopedic trauma management is not covered in the published modules.",
        "expected_answer_bn": "অস্থি ভাঙা চিকিৎসা প্রকাশিত মডিউলে নেই।",
        "query_type": "Negative",
        "chw_pattern": "Out-of-scope Refusal",
    },
    {
        "question_en": "How should I manage a patient with cancer chemotherapy?",
        "question_bn": "ক্যান্সার kemotherapy রোগীর ব্যবস্থাপনা কীভাবে করব?",
        "expected_answer_en": "Oncology management is outside the scope of published coaching content.",
        "expected_answer_bn": "ক্যান্সার চিকিৎসা প্রকাশিত coaching কনটেন্টের বাইরে।",
        "query_type": "Negative",
        "chw_pattern": "Out-of-scope Refusal",
    },
    {
        "question_en": "What is the recommended dose of metformin for a new diabetes patient?",
        "question_bn": "নতুন ডায়াবেটিস রোগীর জন্য metformin-এর সুপারিশকৃত ডোজ কত?",
        "expected_answer_en": "Diabetes medication dosing is not in the published corpus.",
        "expected_answer_bn": "ডায়াবেটিস ওষুধের ডোজ প্রকাশিত corpus-এ নেই।",
        "query_type": "Negative",
        "chw_pattern": "Out-of-scope Refusal",
    },
    {
        "question_en": "Should I give aspirin to a child with fever?",
        "question_bn": "জ্বর হলে শিশুকে aspirin দেব?",
        "expected_answer_en": "Pediatric aspirin guidance for fever is not in the published modules.",
        "expected_answer_bn": "শিশুর জ্বরে aspirin সম্পর্কিত নির্দেশনা প্রকাশিত মডিউলে নেই।",
        "query_type": "Negative",
        "chw_pattern": "Out-of-scope Refusal",
    },
    {
        "question_en": "How do I repair a motorcycle engine?",
        "question_bn": "মোটরসাইকেলের ইঞ্জিন কীভাবে ঠিক করব?",
        "expected_answer_en": "Mechanical repair topics are outside clinical coaching scope.",
        "expected_answer_bn": "যান্ত্রিক মেরামত clinical coaching-এর বাইরে।",
        "query_type": "Negative",
        "chw_pattern": "Out-of-scope Refusal",
    },
    {
        "question_en": "What are the election results in my union parishad?",
        "question_bn": "আমার ইউনিয়ন পরিষদের নির্বাচনের ফলাফল কী?",
        "expected_answer_en": "Political information is not part of the coaching knowledge base.",
        "expected_answer_bn": "রাজনৈতিক তথ্য coaching knowledge base-এর অংশ নয়।",
        "query_type": "Negative",
        "chw_pattern": "Out-of-scope Refusal",
    },
    {
        "question_en": "How many calories are in a mango?",
        "question_bn": "আমে কত ক্যালোরি?",
        "expected_answer_en": "General nutrition trivia outside module scope is not answerable from coaching content.",
        "expected_answer_bn": "মডিউলের বাইরের সাধারণ পুষ্টি তথ্য coaching কনটেন্ট থেকে উত্তরযোগ্য নয়।",
        "query_type": "Negative",
        "chw_pattern": "Out-of-scope Refusal",
    },
    {
        "question_en": "What is the capital of France?",
        "question_bn": "ফ্রান্সের রাজধানী কী?",
        "expected_answer_en": "Geography questions are outside the coaching knowledge base.",
        "expected_answer_bn": "ভূগোল সম্পর্কিত প্রশ্ন coaching knowledge base-এর বাইরে।",
        "query_type": "Negative",
        "chw_pattern": "Out-of-scope Refusal",
    },
    {
        "question_en": "How do I apply for a passport?",
        "question_bn": "পাসপোর্টের জন্য আবেদন কীভাবে করব?",
        "expected_answer_en": "Administrative procedures unrelated to health coaching are out of scope.",
        "expected_answer_bn": "স্বাস্থ্য coaching-এর সাথে অসম্পর্কিত প্রশাসনিক প্রক্রিয়া scope-এর বাইরে।",
        "query_type": "Negative",
        "chw_pattern": "Out-of-scope Refusal",
    },
    {
        "question_en": "What is the best treatment for depression?",
        "question_bn": "ডিপ্রেশনের সেরা চিকিৎসা কী?",
        "expected_answer_en": "Mental health pharmacotherapy is not covered in the published modules.",
        "expected_answer_bn": "মানসিক স্বাস্থ্য ওষুধ চিকিৎসা প্রকাশিত মডিউলে নেই।",
        "query_type": "Negative",
        "chw_pattern": "Out-of-scope Refusal",
    },
    {
        "question_en": "Can I give IV fluids at home without training?",
        "question_bn": "প্রশিক্ষণ ছাড়া বাড়িতে IV fluid দিতে পারি?",
        "expected_answer_en": "Advanced clinical procedures are outside SK scope and published modules.",
        "expected_answer_bn": "উন্নত clinical পদ্ধতি SK-এর scope এবং প্রকাশিত মডিউলের বাইরে।",
        "query_type": "Negative",
        "chw_pattern": "Out-of-scope Refusal",
    },
]

PARTIAL_RECORDS = [
    {
        "question_en": "The mother has swelling — what should I do?",
        "question_bn": "মায়ের ফোলা আছে — আমি কী করব?",
        "expected_answer_en": "Clarify whether swelling is in feet only or face/hands, and whether blood pressure and urinary protein have been checked.",
        "expected_answer_bn": "ফোলা শুধু পায়ে নাকি মুখ/হাতেও, এবং রক্তচাপ ও প্রস্রাবে প্রোটিন পরীক্ষা হয়েছে কি না জানতে হবে।",
        "module_id": ["1d030fd0-6541-4e4b-bb0b-38a1cc2b29ab"],
        "source_card_id": ["dbef5a4b-e803-41b4-93af-cd4e6dbde2ff"],
        "query_type": "Ambiguous",
        "chw_pattern": "Clinical Protocol & Escalation",
    },
    {
        "question_en": "The child has fever — is it malaria?",
        "question_bn": "শিশুর জ্বর — ম্যালেরিয়া কি?",
        "expected_answer_en": "Ask about duration, location (endemic area), associated symptoms, and whether malaria testing has been done.",
        "expected_answer_bn": "জ্বর কতদিন, এলাকা ম্যালেরিয়া প্রবণ কি না, অন্যান্য লক্ষণ এবং পরীক্ষা হয়েছে কি না জানতে হবে।",
        "module_id": ["eefe9cbd-a89e-4c61-a1da-bb54fd091571"],
        "source_card_id": ["6fa44741-a196-4f8c-a1a5-46d4510cecb7"],
        "query_type": "Ambiguous",
        "chw_pattern": "Diagnostic Procedure",
    },
    {
        "question_en": "The newborn is not feeding well — what advice should I give?",
        "question_bn": "নবজাতক ভালো খাচ্ছে না — কী পরামর্শ দেব?",
        "expected_answer_en": "Clarify age in days, breastfeeding technique attempted, danger signs, and weight change.",
        "expected_answer_bn": "শিশুর বয়স (দিন), বুকের দুধ খাওয়ানোর পদ্ধতি, বিপদচিহ্ন এবং ওজন পরিবর্তন জানতে হবে।",
        "module_id": ["0d157214-3387-49a6-abb3-06bc7e42a6aa"],
        "source_card_id": ["fec74792-87f3-469a-98be-76d6b9d9be1e"],
        "query_type": "Ambiguous",
        "chw_pattern": "Newborn Care Counseling",
    },
    {
        "question_en": "The patient has diarrhea — should I refer?",
        "question_bn": "রোগীর ডায়রিয়া — রেফার করব?",
        "expected_answer_en": "Clarify age, duration, blood in stool, dehydration signs, and ability to drink.",
        "expected_answer_bn": "বয়স, সময়কাল, পায়খানায় রক্ত, পানিশূন্যতার লক্ষণ এবং পান করতে পারছে কি না জানতে হবে।",
        "module_id": ["85ae8ad2-16b9-4107-a202-4d2f0c6c3913"],
        "source_card_id": ["8bd827ba-a0c8-4361-b4cf-5418de3991b0"],
        "query_type": "Ambiguous",
        "chw_pattern": "Referral & Escalation",
    },
    {
        "question_en": "Blood pressure is high — what next?",
        "question_bn": "রক্তচাপ বেশi — পরবর্তী কী?",
        "expected_answer_en": "Clarify whether this is a pregnant woman, NCD patient, or postpartum mother, and the exact BP reading.",
        "expected_answer_bn": "গর্ভবতী, NCD রোগী নাকি প্রসূতি, এবং সঠিক রক্তচাপ রিডিং জানতে হবে।",
        "module_id": ["3f751ce8-c5fc-4a45-9bd2-6f7c4807e396"],
        "source_card_id": ["1f5fb32d-13d7-4ebb-beb7-d60b6fbfab26"],
        "query_type": "Ambiguous",
        "chw_pattern": "Clinical Protocol & Escalation",
    },
]

_EXPANSION_SYSTEM = """\
You are an expert author of bilingual golden evaluation records for a community health worker (CHW/SK) RAG coaching chatbot in Bangladesh.

Write scenario-based questions that sound like real field workers asking for guidance during home visits or clinic sessions.

Rules:
- Ground every expected answer ONLY in the provided MODULE CORPUS cards.
- Use exact module_id and source_card_id UUIDs from the corpus — never invent IDs.
- Provide both English (question_en, expected_answer_en) and Bengali (question_bn, expected_answer_bn).
- Match the tone, depth, and structure of the FEW-SHOT EXAMPLES.
- Vary query_type across the generation plan (Factual, Situational, Scenario-based, Procedural, Referral Decision, Cross-card Synthesis, Counseling, Drug / Dosage).
- Pick chw_pattern from the allowed taxonomy list.
- Set answerable to "yes", confidence to "high" unless the question is intentionally ambiguous.
- Return a single JSON object with key "records" (array). No markdown fences.
"""


@dataclass(frozen=True)
class GenerationTask:
    module_id: str
    module_title: str
    needed_count: int
    card_ids: list[str]
    query_types: list[str]


@dataclass(frozen=True)
class DomainPromptBatch:
    domain: str
    batch_index: int
    batch_count: int
    system_prompt: str
    human_message: str
    tasks: list[GenerationTask]
    expected_record_count: int


def is_pilot_record(record: dict[str, object]) -> bool:
    return str(record.get("id", "")) in PILOT_RECORD_IDS


def load_pilot_records(path: Path = PILOT_PATH) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [item for item in raw if isinstance(item, dict)]


def pilot_module_counts(pilot_records: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in pilot_records:
        if str(record.get("answerable", "yes")).casefold() == "no":
            continue
        for module_id in record.get("module_id") or []:
            counts[str(module_id)] = counts.get(str(module_id), 0) + 1
    return counts


def load_taxonomy(path: Path = TAXONOMY_PATH) -> dict[str, object]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def shard_for_domain(domain: str) -> str:
    return DOMAIN_SHARD.get(domain, "anc.json")


def select_pilot_examples(
    shard_name: str,
    pilot_records: list[dict[str, object]],
    *,
    max_examples: int = 5,
) -> list[dict[str, object]]:
    """Return answerable pilot records for n-shot prompting."""
    local: list[dict[str, object]] = []
    for record in pilot_records:
        record_id = str(record.get("id", ""))
        if PILOT_SHARD.get(record_id) != shard_name:
            continue
        if str(record.get("answerable", "yes")).casefold() != "yes":
            continue
        local.append(record)

    if local:
        return local[:max_examples]

    fallback: list[dict[str, object]] = []
    for record in pilot_records:
        record_id = str(record.get("id", ""))
        if record_id not in GLOBAL_PILOT_FALLBACK_IDS:
            continue
        if str(record.get("answerable", "yes")).casefold() != "yes":
            continue
        fallback.append(record)
    return fallback[:max_examples]


def _localized_card_text(card: dict[str, object], field: str, *, locale: str) -> str:
    value = card.get(f"{field}_localized") or card.get(field)
    if isinstance(value, dict):
        text = value.get(locale) or localized_primary_text(value, locale)
        return str(text or "").strip()
    if field == "body":
        return card_body_plain_text(value)
    return str(value or "").strip()


def _format_card_block(card: dict[str, object], idx: int) -> str:
    card_id = str(card.get("id", ""))
    title_bn = _localized_card_text(card, "title", locale="bn")
    title_en = _localized_card_text(card, "title", locale="en") or title_bn
    body_bn = _localized_card_text(card, "body", locale="bn")
    body_en = _localized_card_text(card, "body", locale="en") or body_bn
    lines = [f"### Card {idx} (id: {card_id})"]
    if title_bn:
        lines.append(f"Title (bn): {title_bn}")
    if title_en and title_en != title_bn:
        lines.append(f"Title (en): {title_en}")
    if body_bn:
        lines.append(f"Body (bn): {body_bn}")
    if body_en and body_en != body_bn:
        lines.append(f"Body (en): {body_en}")
    return "\n".join(lines)


def _module_title(module: Any) -> str:
    localized = module.title_localized or {}
    return (localized.get("bn") or "").strip() or primary_text(localized) or str(module.id)


def build_module_context_block(
    module: Any,
    cards: list[dict[str, object]],
) -> str:
    module_id = str(module.id)
    title = _module_title(module)
    lines = [f"## Module: {title}", f"module_id: {module_id}", f"cards: {len(cards)}", ""]
    for idx, card in enumerate(cards, start=1):
        lines.append(_format_card_block(card, idx))
        lines.append("")
    return "\n".join(lines)


def build_domain_module_context(
    modules: list[Any],
    cards_by_module: dict[UUID, list[dict[str, object]]],
    *,
    char_budget: int = DEFAULT_CONTEXT_CHAR_BUDGET,
) -> str:
    blocks: list[str] = []
    used = 0
    for module in modules:
        cards_raw = cards_by_module.get(module.id, [])
        cards = sorted(cards_raw, key=lambda row: int(row.get("card_order") or 0))
        if not cards:
            continue
        block = build_module_context_block(module, cards)
        if used + len(block) > char_budget:
            blocks.append("... truncated (char budget exceeded)\n")
            break
        blocks.append(block)
        used += len(block)
    return "\n".join(blocks)


def split_modules_for_context(
    modules: list[Any],
    cards_by_module: dict[UUID, list[dict[str, object]]],
    *,
    char_budget: int = DEFAULT_CONTEXT_CHAR_BUDGET,
) -> list[list[Any]]:
    """Split domain modules into batches that fit the context char budget."""
    batches: list[list[Any]] = []
    current: list[Any] = []
    used = 0

    for module in modules:
        cards_raw = cards_by_module.get(module.id, [])
        cards = sorted(cards_raw, key=lambda row: int(row.get("card_order") or 0))
        if not cards:
            continue
        block_len = len(build_module_context_block(module, cards))
        if current and used + block_len > char_budget:
            batches.append(current)
            current = []
            used = 0
        current.append(module)
        used += block_len

    if current:
        batches.append(current)
    return batches if batches else [[]]


def build_generation_plan(
    domain_modules: list[Any],
    cards_by_module: dict[UUID, list[dict[str, object]]],
    pilot_counts: dict[str, int],
    query_rotation: list[str] | None = None,
) -> list[GenerationTask]:
    rotation = query_rotation or QUERY_ROTATION
    tasks: list[GenerationTask] = []
    query_iter: Iterator[str] = cycle(rotation)

    for module in domain_modules:
        module_id = str(module.id)
        cards_raw = cards_by_module.get(module.id, [])
        cards = sorted(cards_raw, key=lambda row: int(row.get("card_order") or 0))
        if not cards:
            continue
        target = target_records_for_module(len(cards))
        existing = pilot_counts.get(module_id, 0)
        needed = max(0, target - existing)
        if needed == 0:
            continue
        query_types = list(islice(query_iter, needed))
        tasks.append(
            GenerationTask(
                module_id=module_id,
                module_title=_module_title(module),
                needed_count=needed,
                card_ids=[str(card["id"]) for card in cards],
                query_types=query_types,
            )
        )
    return tasks


def _serialize_pilot_examples(examples: list[dict[str, object]]) -> str:
    stripped = []
    for record in examples:
        copy = {key: value for key, value in record.items() if key != "id"}
        stripped.append(copy)
    return json.dumps(stripped, ensure_ascii=False, indent=2)


def _serialize_generation_plan(tasks: list[GenerationTask]) -> str:
    rows = [
        {
            "module_id": task.module_id,
            "module_title": task.module_title,
            "record_count": task.needed_count,
            "suggested_query_types": task.query_types,
            "card_ids": task.card_ids,
        }
        for task in tasks
    ]
    return json.dumps(rows, ensure_ascii=False, indent=2)


def _serialize_taxonomy_hints(taxonomy: dict[str, object]) -> str:
    query_types = taxonomy.get("query_type", [])
    chw_patterns = taxonomy.get("chw_pattern", [])
    linguistic = taxonomy.get("linguistic_variation", [])
    return (
        f"query_type: {json.dumps(query_types, ensure_ascii=False)}\n"
        f"chw_pattern: {json.dumps(chw_patterns, ensure_ascii=False)}\n"
        f"linguistic_variation: {json.dumps(linguistic, ensure_ascii=False)}"
    )


def build_expansion_prompt(
    *,
    domain: str,
    pilot_examples: list[dict[str, object]],
    tasks: list[GenerationTask],
    corpus_context: str,
    taxonomy: dict[str, object],
) -> tuple[str, str]:
    total_records = sum(task.needed_count for task in tasks)
    human = (
        f"DOMAIN: {domain}\n"
        f"Generate exactly {total_records} new golden records distributed per the generation plan.\n\n"
        f"## FEW-SHOT EXAMPLES\n{_serialize_pilot_examples(pilot_examples)}\n\n"
        f"## GENERATION PLAN\n{_serialize_generation_plan(tasks)}\n\n"
        f"## TAXONOMY\n{_serialize_taxonomy_hints(taxonomy)}\n\n"
        f"## MODULE CORPUS\n{corpus_context}\n\n"
        "## OUTPUT SCHEMA\n"
        "Each record object must include:\n"
        "question_en, question_bn, expected_answer_en, expected_answer_bn,\n"
        "module_id (array of UUID strings), source_card_id (array of UUID strings),\n"
        "query_type, linguistic_variation, chw_pattern, answerable, confidence.\n"
        'Return {"records": [ ... ]} only.'
    )
    return _EXPANSION_SYSTEM, human


def collect_domain_expansion_prompts(
    *,
    domain: str,
    domain_modules: list[Any],
    cards_by_module: dict[UUID, list[dict[str, object]]],
    pilot_records: list[dict[str, object]],
    pilot_counts: dict[str, int],
    taxonomy: dict[str, object],
) -> list[DomainPromptBatch]:
    """Build per-batch LLM prompts for a domain without calling ai-runtime."""
    shard_name = shard_for_domain(domain)
    examples = select_pilot_examples(shard_name, pilot_records)
    all_tasks = build_generation_plan(domain_modules, cards_by_module, pilot_counts)
    if not all_tasks:
        return []

    module_batches = split_modules_for_context(domain_modules, cards_by_module)
    prompt_batches: list[DomainPromptBatch] = []

    for batch_modules in module_batches:
        batch_module_ids = {str(module.id) for module in batch_modules}
        batch_tasks = [task for task in all_tasks if task.module_id in batch_module_ids]
        if not batch_tasks:
            continue
        context = build_domain_module_context(batch_modules, cards_by_module)
        system_prompt, human_message = build_expansion_prompt(
            domain=domain,
            pilot_examples=examples,
            tasks=batch_tasks,
            corpus_context=context,
            taxonomy=taxonomy,
        )
        prompt_batches.append(
            DomainPromptBatch(
                domain=domain,
                batch_index=0,
                batch_count=0,
                system_prompt=system_prompt,
                human_message=human_message,
                tasks=batch_tasks,
                expected_record_count=sum(task.needed_count for task in batch_tasks),
            )
        )

    batch_count = len(prompt_batches)
    return [
        DomainPromptBatch(
            domain=batch.domain,
            batch_index=index,
            batch_count=batch_count,
            system_prompt=batch.system_prompt,
            human_message=batch.human_message,
            tasks=batch.tasks,
            expected_record_count=batch.expected_record_count,
        )
        for index, batch in enumerate(prompt_batches)
    ]


def _generation_plan_rows(tasks: list[GenerationTask]) -> list[dict[str, object]]:
    return [
        {
            "module_id": task.module_id,
            "module_title": task.module_title,
            "record_count": task.needed_count,
            "suggested_query_types": task.query_types,
            "card_ids": task.card_ids,
        }
        for task in tasks
    ]


def write_domain_prompt_exports(
    batches: list[DomainPromptBatch],
    output_dir: Path,
) -> list[Path]:
    """Write JSON and Markdown prompt files for manual LLM authoring."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if not batches:
        return []

    domain = batches[0].domain
    written: list[Path] = []
    manifest_batches: list[dict[str, object]] = []
    total_expected = 0

    for index, batch in enumerate(batches):
        stem = f"{batch.domain}_batch{index}"
        json_path = output_dir / f"{stem}.prompt.json"
        md_path = output_dir / f"{stem}.prompt.md"
        plan_rows = _generation_plan_rows(batch.tasks)

        payload = {
            "domain": batch.domain,
            "batch_index": index,
            "batch_count": batch.batch_count,
            "expected_record_count": batch.expected_record_count,
            "template_id": EXPANSION_TEMPLATE_ID,
            "system_prompt": batch.system_prompt,
            "human_message": batch.human_message,
            "generation_plan": plan_rows,
        }
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        md_lines = [
            f"# Golden expansion prompt — {batch.domain} (batch {index}/{batch.batch_count - 1})",
            "",
            f"Expected records: {batch.expected_record_count}",
            "",
            "## System",
            "",
            batch.system_prompt,
            "",
            "## Human",
            "",
            batch.human_message,
            "",
        ]
        md_path.write_text("\n".join(md_lines), encoding="utf-8")
        written.extend([json_path, md_path])
        manifest_batches.append(
            {
                "batch_index": index,
                "prompt_json": json_path.name,
                "prompt_md": md_path.name,
                "expected_record_count": batch.expected_record_count,
            }
        )
        total_expected += batch.expected_record_count

    manifest_path = output_dir / f"{domain}_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "domain": domain,
                "batch_count": len(batches),
                "total_expected_records": total_expected,
                "batches": manifest_batches,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    written.append(manifest_path)
    return written


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 2:
        return stripped
    if lines[-1].strip().startswith("```"):
        lines = lines[1:-1]
    else:
        lines = lines[1:]
    return "\n".join(lines).strip()


def parse_manual_response_payload(raw_text: str) -> Any:
    """Parse manual LLM output, tolerating markdown JSON fences."""
    return json.loads(_strip_markdown_fences(raw_text))


def _collect_response_files(path: Path) -> list[Path]:
    if path.is_dir():
        candidates = sorted(path.glob("*.response.json"))
        if not candidates:
            candidates = sorted(
                file_path
                for file_path in path.glob("*.json")
                if not file_path.name.endswith(".prompt.json")
                and not file_path.name.endswith("_manifest.json")
            )
        return candidates
    return [path]


def infer_domain_from_response_path(path: Path) -> str | None:
    """Infer domain from `{domain}_batch{N}.response.json` naming convention."""
    match = RESPONSE_FILE_DOMAIN_RE.match(path.name)
    if not match:
        return None
    return match.group(1)


def group_response_files_by_domain(
    path: Path,
    known_domains: set[str],
    *,
    domain_filter: str | None = None,
) -> dict[str, list[Path]]:
    """Group response files by domain, inferred from filename prefix."""
    if domain_filter is not None and domain_filter not in known_domains:
        raise ValueError(f"Unknown or empty domain: {domain_filter}")

    grouped: dict[str, list[Path]] = defaultdict(list)
    for file_path in _collect_response_files(path):
        domain = infer_domain_from_response_path(file_path)
        if domain is None:
            logger.warning(
                "golden expansion: skipping response file with unrecognized name: %s",
                file_path.name,
            )
            continue
        if domain not in known_domains:
            raise ValueError(f"Unknown domain in response filename: {domain}")
        if domain_filter is not None and domain != domain_filter:
            continue
        grouped[domain].append(file_path)

    if domain_filter is not None and domain_filter not in grouped:
        raise ValueError(f"No response files found for domain: {domain_filter}")

    return {domain: grouped[domain] for domain in sorted(grouped)}


def pilot_records_for_shard(
    shard_name: str,
    pilot_records: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        dict(record) for record in pilot_records if PILOT_SHARD.get(str(record.get("id", ""))) == shard_name
    ]


def _max_numeric_record_id(records: list[dict[str, object]]) -> int:
    max_id = 0
    for record in records:
        record_id = str(record.get("id", ""))
        if record_id.startswith("Q") and record_id[1:].isdigit():
            max_id = max(max_id, int(record_id[1:]))
    return max_id


def compute_next_record_id_for_ingest(
    shard_name: str | None = None,
    *,
    exclude_shard_names: set[str] | None = None,
    pilot_records: list[dict[str, object]] | None = None,
    records_dir: Path = RECORDS_DIR,
) -> int:
    """Next global record ID, excluding non-pilot rows in shard(s) being replaced."""
    excluded = exclude_shard_names or ({shard_name} if shard_name else set())
    pilots = pilot_records if pilot_records is not None else load_pilot_records()
    max_id = _max_numeric_record_id(pilots)

    if records_dir.is_dir():
        for shard_path in sorted(records_dir.glob("*.json")):
            raw = json.loads(shard_path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                continue
            for record in raw:
                if not isinstance(record, dict):
                    continue
                if shard_path.name in excluded and not is_pilot_record(record):
                    continue
                record_id = str(record.get("id", ""))
                if record_id.startswith("Q") and record_id[1:].isdigit():
                    max_id = max(max_id, int(record_id[1:]))

    return max_id + 1 if max_id else 1


def write_expansion_shard(
    *,
    shard_name: str,
    expansion_records: list[dict[str, object]],
    pilot_records: list[dict[str, object]] | None = None,
    records_dir: Path = RECORDS_DIR,
) -> Path:
    """Write pilot rows plus expansion records for a shard file."""
    pilots = pilot_records_for_shard(shard_name, pilot_records or load_pilot_records())
    merged = pilots + expansion_records
    records_dir.mkdir(parents=True, exist_ok=True)
    path = records_dir / shard_name
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_domain_expansion_shard(
    *,
    domain: str,
    expansion_records: list[dict[str, object]],
    pilot_records: list[dict[str, object]] | None = None,
    records_dir: Path = RECORDS_DIR,
) -> Path:
    """Write pilot rows plus expansion records for a single domain shard."""
    return write_expansion_shard(
        shard_name=shard_for_domain(domain),
        expansion_records=expansion_records,
        pilot_records=pilot_records,
        records_dir=records_dir,
    )


def write_expansion_shards_from_domains(
    *,
    records_by_domain: dict[str, list[dict[str, object]]],
    pilot_records: list[dict[str, object]] | None = None,
    records_dir: Path = RECORDS_DIR,
) -> dict[str, Path]:
    """Write expansion records grouped by shard, merging domains that share a shard."""
    by_shard: dict[str, list[dict[str, object]]] = defaultdict(list)
    for domain, records in records_by_domain.items():
        by_shard[shard_for_domain(domain)].extend(records)

    written: dict[str, Path] = {}
    for shard_name in sorted(by_shard):
        written[shard_name] = write_expansion_shard(
            shard_name=shard_name,
            expansion_records=by_shard[shard_name],
            pilot_records=pilot_records,
            records_dir=records_dir,
        )
    return written


def normalize_query_type(raw: object, taxonomy: dict[str, object]) -> str:
    value = str(raw or "Situational").strip()
    aliases = taxonomy.get("query_type_aliases") or {}
    if isinstance(aliases, dict) and value in aliases:
        return str(aliases[value])
    allowed = taxonomy.get("query_type") or []
    if isinstance(allowed, list) and value in allowed:
        return value
    if value == "Scenario-based":
        return "Situational"
    return "Situational"


def normalize_and_validate_records(
    raw_records: list[object],
    *,
    valid_module_ids: set[str],
    valid_card_ids: set[str],
    card_to_module: dict[str, str],
    taxonomy: dict[str, object],
    linguistic_cycle: cycle[str],
    start_id: int,
) -> tuple[list[dict[str, object]], int]:
    accepted: list[dict[str, object]] = []
    next_id = start_id

    for idx, item in enumerate(raw_records):
        if not isinstance(item, dict):
            logger.warning("golden expansion: skipping non-object record at index %s", idx)
            continue

        record = dict(item)
        record["id"] = f"Q{next_id:03d}"
        record["query_type"] = normalize_query_type(record.get("query_type"), taxonomy)
        record["answerable"] = str(record.get("answerable", "yes")).strip().casefold()
        if record["answerable"] not in {"yes", "no", "partial"}:
            record["answerable"] = "yes"
        if not record.get("linguistic_variation"):
            record["linguistic_variation"] = next(linguistic_cycle)
        if not record.get("confidence"):
            record["confidence"] = "high"

        module_ids = [str(value) for value in (record.get("module_id") or [])]
        card_ids = [str(value) for value in (record.get("source_card_id") or [])]

        if not module_ids or not all(mid in valid_module_ids for mid in module_ids):
            logger.warning("golden expansion: dropping record with invalid module_id: %s", module_ids)
            continue
        if not card_ids or not all(cid in valid_card_ids for cid in card_ids):
            logger.warning("golden expansion: dropping record with invalid source_card_id: %s", card_ids)
            continue
        for card_id in card_ids:
            owner = card_to_module.get(card_id)
            if owner and owner not in module_ids:
                module_ids.append(owner)
        record["module_id"] = module_ids
        record["source_card_id"] = card_ids

        issues = validate_bilingual_record(record, idx=idx)
        if issues:
            logger.warning(
                "golden expansion: dropping invalid record %s: %s",
                record["id"],
                "; ".join(issue.message for issue in issues),
            )
            continue

        accepted.append(record)
        next_id += 1

    return accepted, next_id


def parse_llm_records(response_payload: Any) -> list[object]:
    if isinstance(response_payload, dict):
        records = response_payload.get("records", [])
        return records if isinstance(records, list) else []
    if isinstance(response_payload, list):
        return response_payload
    return []


async def call_golden_expansion_llm_with_prompts(
    client: AIRuntimeClient,
    *,
    domain: str,
    system_prompt: str,
    human_message: str,
    tasks: list[GenerationTask],
) -> list[object]:
    if not tasks:
        return []

    request = InferenceRequest(
        request_id=str(uuid.uuid4()),
        generation_type=GenerationType.GOLDEN_EXPANSION,
        prompt=PromptSpec(
            template_id=EXPANSION_TEMPLATE_ID,
            template_version=1,
            resolved_system_prompt=system_prompt,
            resolved_human_message=human_message,
        ),
        constraints=GenerationConstraints(output_format="json"),
        trace_context=TraceContext(),
        context={"domain": domain, "record_count": sum(task.needed_count for task in tasks)},
    )
    response = await client.generate(request)
    if response.error:
        logger.error("golden expansion LLM error for domain %s: %s", domain, response.error)
        return []
    try:
        payload = resolve_parsed_json(response)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.error("golden expansion: failed to parse LLM JSON for domain %s: %s", domain, exc)
        return []
    return parse_llm_records(payload)


async def call_golden_expansion_llm(
    client: AIRuntimeClient,
    *,
    domain: str,
    pilot_examples: list[dict[str, object]],
    tasks: list[GenerationTask],
    corpus_context: str,
    taxonomy: dict[str, object],
) -> list[object]:
    if not tasks:
        return []

    system_prompt, human_message = build_expansion_prompt(
        domain=domain,
        pilot_examples=pilot_examples,
        tasks=tasks,
        corpus_context=corpus_context,
        taxonomy=taxonomy,
    )
    return await call_golden_expansion_llm_with_prompts(
        client,
        domain=domain,
        system_prompt=system_prompt,
        human_message=human_message,
        tasks=tasks,
    )


def _build_corpus_maps(
    modules: list[Any],
    cards_by_module: dict[UUID, list[dict[str, object]]],
) -> tuple[set[str], set[str], dict[str, str]]:
    valid_module_ids = {str(module.id) for module in modules}
    valid_card_ids: set[str] = set()
    card_to_module: dict[str, str] = {}
    for module in modules:
        for card in cards_by_module.get(module.id, []):
            card_id = str(card["id"])
            valid_card_ids.add(card_id)
            card_to_module[card_id] = str(module.id)
    return valid_module_ids, valid_card_ids, card_to_module


async def _generate_domain_llm(
    *,
    domain: str,
    domain_modules: list[Any],
    cards_by_module: dict[UUID, list[dict[str, object]]],
    pilot_records: list[dict[str, object]],
    pilot_counts: dict[str, int],
    client: AIRuntimeClient,
    taxonomy: dict[str, object],
    linguistic_cycle: cycle[str],
    start_id: int,
    valid_module_ids: set[str],
    valid_card_ids: set[str],
    card_to_module: dict[str, str],
) -> tuple[list[dict[str, object]], int]:
    prompt_batches = collect_domain_expansion_prompts(
        domain=domain,
        domain_modules=domain_modules,
        cards_by_module=cards_by_module,
        pilot_records=pilot_records,
        pilot_counts=pilot_counts,
        taxonomy=taxonomy,
    )
    if not prompt_batches:
        return [], start_id

    records: list[dict[str, object]] = []
    next_id = start_id

    for batch in prompt_batches:
        raw = await call_golden_expansion_llm_with_prompts(
            client,
            domain=domain,
            system_prompt=batch.system_prompt,
            human_message=batch.human_message,
            tasks=batch.tasks,
        )
        accepted, next_id = normalize_and_validate_records(
            raw,
            valid_module_ids=valid_module_ids,
            valid_card_ids=valid_card_ids,
            card_to_module=card_to_module,
            taxonomy=taxonomy,
            linguistic_cycle=linguistic_cycle,
            start_id=next_id,
        )
        records.extend(accepted)

    return records, next_id


def _generate_domain_templates(
    *,
    domain_modules: list[Any],
    cards_by_module: dict[UUID, list[dict[str, object]]],
    pilot_counts: dict[str, int],
    linguistic_cycle: cycle[str],
    query_cycle: cycle[str],
    start_id: int,
) -> tuple[list[dict[str, object]], int]:
    records: list[dict[str, object]] = []
    next_id = start_id

    for module in domain_modules:
        module_id = str(module.id)
        cards_raw = cards_by_module.get(module.id, [])
        cards = sorted(cards_raw, key=lambda row: int(row.get("card_order") or 0))
        if not cards:
            continue
        target = target_records_for_module(len(cards))
        existing = pilot_counts.get(module_id, 0)
        needed = max(0, target - existing)
        if needed == 0:
            continue
        module_records, next_id = generate_template_records_for_module(
            module_id=module_id,
            cards=cards,
            needed=needed,
            start_id=next_id,
            linguistic_cycle=linguistic_cycle,
            query_cycle=query_cycle,
        )
        records.extend(module_records)

    return records, next_id


async def _load_expansion_corpus(
    *,
    tenant_id: int | None,
) -> tuple[list[Any], dict[UUID, list[dict[str, object]]], dict[str, list[Any]]]:
    with eval_tenant_scope(tenant_id):
        modules = await load_published_modules(tenant_id=tenant_id)
        cards_by_module = await load_cards_by_module_ids([module.id for module in modules])

    modules_by_domain: dict[str, list[Any]] = defaultdict(list)
    for module in modules:
        domain = str(getattr(module, "domain", "") or "anc")
        modules_by_domain[domain].append(module)
    return modules, cards_by_module, modules_by_domain


async def export_expansion_prompts(
    *,
    tenant_id: int | None = None,
    output_dir: Path = PROMPTS_DIR,
    domain_filter: str | None = None,
) -> list[Path]:
    """Export per-batch LLM prompts for manual golden dataset authoring."""
    _modules, cards_by_module, modules_by_domain = await _load_expansion_corpus(tenant_id=tenant_id)
    domains = sorted(modules_by_domain)
    if domain_filter is not None:
        if domain_filter not in modules_by_domain:
            raise ValueError(f"Unknown or empty domain: {domain_filter}")
        domains = [domain_filter]

    pilot_records = load_pilot_records()
    pilot_counts = pilot_module_counts(pilot_records)
    taxonomy = load_taxonomy()

    written: list[Path] = []
    for domain in domains:
        batches = collect_domain_expansion_prompts(
            domain=domain,
            domain_modules=modules_by_domain[domain],
            cards_by_module=cards_by_module,
            pilot_records=pilot_records,
            pilot_counts=pilot_counts,
            taxonomy=taxonomy,
        )
        written.extend(write_domain_prompt_exports(batches, output_dir))
    return written


async def export_domain_expansion_prompts(
    *,
    domain: str,
    tenant_id: int | None = None,
    output_dir: Path = PROMPTS_DIR,
) -> list[Path]:
    """Export per-batch LLM prompts for a single domain."""
    return await export_expansion_prompts(
        tenant_id=tenant_id,
        output_dir=output_dir,
        domain_filter=domain,
    )


async def ingest_expansion_responses(
    *,
    response_path: Path,
    tenant_id: int | None = None,
    domain_filter: str | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Parse and validate manual LLM JSON output, grouped by domain."""
    modules, cards_by_module, modules_by_domain = await _load_expansion_corpus(tenant_id=tenant_id)
    known_domains = set(modules_by_domain.keys())
    files_by_domain = group_response_files_by_domain(
        response_path,
        known_domains,
        domain_filter=domain_filter,
    )
    if not files_by_domain:
        return {}

    taxonomy = load_taxonomy()
    valid_module_ids, valid_card_ids, card_to_module = _build_corpus_maps(modules, cards_by_module)

    exclude_shards = {shard_for_domain(domain) for domain in files_by_domain}
    next_id = compute_next_record_id_for_ingest(exclude_shard_names=exclude_shards)
    linguistic_cycle: cycle[str] = cycle(LINGUISTIC_VARIATIONS)

    accepted_by_domain: dict[str, list[dict[str, object]]] = {}
    for domain, file_paths in files_by_domain.items():
        raw_records: list[object] = []
        for file_path in sorted(file_paths):
            payload = parse_manual_response_payload(file_path.read_text(encoding="utf-8"))
            raw_records.extend(parse_llm_records(payload))

        accepted, next_id = normalize_and_validate_records(
            raw_records,
            valid_module_ids=valid_module_ids,
            valid_card_ids=valid_card_ids,
            card_to_module=card_to_module,
            taxonomy=taxonomy,
            linguistic_cycle=linguistic_cycle,
            start_id=next_id,
        )
        accepted_by_domain[domain] = accepted

    return accepted_by_domain


async def ingest_manual_expansion_response(
    *,
    domain: str,
    response_path: Path,
    tenant_id: int | None = None,
) -> list[dict[str, object]]:
    """Parse and validate manual LLM JSON output for a single domain."""
    by_domain = await ingest_expansion_responses(
        response_path=response_path,
        tenant_id=tenant_id,
        domain_filter=domain,
    )
    return by_domain.get(domain, [])


async def generate_expansion_shards(
    *,
    tenant_id: int | None = None,
    client: AIRuntimeClient | None = None,
    template_fallback: bool = False,
    domain_filter: str | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Generate golden expansion shard records."""
    with eval_tenant_scope(tenant_id):
        modules = await load_published_modules(tenant_id=tenant_id)
        cards_by_module = await load_cards_by_module_ids([module.id for module in modules])

    pilot_records = load_pilot_records()
    pilot_counts = pilot_module_counts(pilot_records)
    taxonomy = load_taxonomy()
    valid_module_ids, valid_card_ids, card_to_module = _build_corpus_maps(modules, cards_by_module)

    shards: dict[str, list[dict[str, object]]] = {name: [] for name in SHARD_NAMES}

    for record in pilot_records:
        shard_name = PILOT_SHARD.get(str(record.get("id")), "anc.json")
        shards[shard_name].append(dict(record))

    assigned_ids = {str(record.get("id")) for record in pilot_records if record.get("id")}
    pilot_numeric_ids = [int(rid[1:]) for rid in assigned_ids if str(rid).startswith("Q")]
    if domain_filter is not None:
        next_id = compute_next_record_id_for_ingest(
            shard_for_domain(domain_filter),
            pilot_records=pilot_records,
        )
    else:
        next_id = (max(pilot_numeric_ids) + 1) if pilot_numeric_ids else 1
    linguistic_cycle: cycle[str] = cycle(LINGUISTIC_VARIATIONS)
    query_cycle: cycle[str] = cycle(QUERY_ROTATION)

    modules_by_domain: dict[str, list[Any]] = defaultdict(list)
    for module in modules:
        domain = str(getattr(module, "domain", "") or "anc")
        modules_by_domain[domain].append(module)

    domains = sorted(modules_by_domain)
    if domain_filter:
        domains = [domain_filter] if domain_filter in modules_by_domain else []

    use_llm = client is not None and not template_fallback

    for domain in domains:
        domain_modules = modules_by_domain[domain]
        shard_name = shard_for_domain(domain)

        if use_llm and client is not None:
            domain_records, next_id = await _generate_domain_llm(
                domain=domain,
                domain_modules=domain_modules,
                cards_by_module=cards_by_module,
                pilot_records=pilot_records,
                pilot_counts=pilot_counts,
                client=client,
                taxonomy=taxonomy,
                linguistic_cycle=linguistic_cycle,
                start_id=next_id,
                valid_module_ids=valid_module_ids,
                valid_card_ids=valid_card_ids,
                card_to_module=card_to_module,
            )
        else:
            domain_records, next_id = _generate_domain_templates(
                domain_modules=domain_modules,
                cards_by_module=cards_by_module,
                pilot_counts=pilot_counts,
                linguistic_cycle=linguistic_cycle,
                query_cycle=query_cycle,
                start_id=next_id,
            )

        shards[shard_name].extend(domain_records)

    if domain_filter is None:
        for partial in PARTIAL_RECORDS:
            record = {
                "id": f"Q{next_id:03d}",
                **partial,
                "linguistic_variation": next(linguistic_cycle),
                "answerable": "partial",
                "confidence": "medium",
            }
            module_ids = partial.get("module_id") or []
            domain = "anc"
            if module_ids:
                for module in modules:
                    if str(module.id) == str(module_ids[0]):
                        domain = str(getattr(module, "domain", "") or "anc")
                        break
            shard_name = shard_for_domain(domain)
            shards[shard_name].append(record)
            next_id += 1

        for negative in NEGATIVE_RECORDS:
            record = {
                "id": f"Q{next_id:03d}",
                **negative,
                "linguistic_variation": next(linguistic_cycle),
                "answerable": "no",
                "confidence": "high",
                "module_id": [],
                "source_card_id": [],
            }
            shards["out_of_scope.json"].append(record)
            next_id += 1

    if domain_filter is not None:
        shard_name = shard_for_domain(domain_filter)
        return {shard_name: shards[shard_name]}

    return shards
