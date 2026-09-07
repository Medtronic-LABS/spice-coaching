"""Schema and consistency validation for bilingual golden records."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from eval.rag.golden_manifest import load_golden_source_array

_ID_PATTERN = re.compile(r"^Q[0-9]{3,}$")
_BILINGUAL_REQUIRED = (
    "question_en",
    "question_bn",
    "expected_answer_en",
    "expected_answer_bn",
)


@dataclass(frozen=True)
class ValidationIssue:
    record_id: str
    message: str


def _record_id(item: dict[str, object], idx: int) -> str:
    raw_id = item.get("id")
    if raw_id is None:
        return f"index_{idx}"
    return str(raw_id)


def _parse_uuid_list(raw: object, *, field: str, record_id: str) -> list[str] | None:
    if raw is None:
        return []
    if not isinstance(raw, list):
        return None
    values: list[str] = []
    for value in raw:
        try:
            values.append(str(UUID(str(value))))
        except ValueError:
            return None
    return values


def validate_bilingual_record(item: dict[str, object], *, idx: int) -> list[ValidationIssue]:
    record_id = _record_id(item, idx)
    issues: list[ValidationIssue] = []

    raw_id = item.get("id")
    if raw_id is None:
        issues.append(ValidationIssue(record_id, "missing id"))
    elif not _ID_PATTERN.match(str(raw_id)):
        issues.append(ValidationIssue(record_id, f"invalid id format: {raw_id!r}"))

    for field in _BILINGUAL_REQUIRED:
        value = item.get(field)
        if not value or not str(value).strip():
            issues.append(ValidationIssue(record_id, f"missing or empty {field}"))

    module_ids = _parse_uuid_list(item.get("module_id"), field="module_id", record_id=record_id)
    if module_ids is None:
        issues.append(ValidationIssue(record_id, "module_id must be a list of UUID strings"))
        module_ids = []

    card_ids = _parse_uuid_list(item.get("source_card_id"), field="source_card_id", record_id=record_id)
    if card_ids is None:
        issues.append(ValidationIssue(record_id, "source_card_id must be a list of UUID strings"))
        card_ids = []

    answerable = str(item.get("answerable", "yes")).strip().casefold()
    query_type = str(item.get("query_type", "")).strip().casefold()

    if answerable not in {"yes", "no", "partial"}:
        issues.append(ValidationIssue(record_id, f"invalid answerable: {item.get('answerable')!r}"))

    if answerable == "no":
        if module_ids:
            issues.append(ValidationIssue(record_id, "answerable=no requires empty module_id"))
        if card_ids and query_type != "negative":
            issues.append(ValidationIssue(record_id, "answerable=no requires empty source_card_id"))
    elif answerable in {"yes", "partial"}:
        if not module_ids:
            issues.append(ValidationIssue(record_id, f"answerable={answerable} requires non-empty module_id"))
        if answerable == "yes" and not card_ids and query_type != "negative":
            issues.append(ValidationIssue(record_id, "answerable=yes requires non-empty source_card_id"))

    if not str(item.get("query_type", "")).strip():
        issues.append(ValidationIssue(record_id, "missing query_type"))

    return issues


def validate_unique_ids(records: list[dict[str, object]]) -> list[ValidationIssue]:
    seen: dict[str, int] = {}
    issues: list[ValidationIssue] = []
    for idx, item in enumerate(records):
        record_id = _record_id(item, idx)
        if record_id in seen:
            issues.append(ValidationIssue(record_id, f"duplicate id (first seen at index {seen[record_id]})"))
        else:
            seen[record_id] = idx
    return issues


def validate_golden_dataset(path: Path) -> list[ValidationIssue]:
    raw_records = load_golden_source_array(path)
    records = [item for item in raw_records if isinstance(item, dict)]
    if len(records) != len(raw_records):
        return [ValidationIssue("dataset", "all records must be JSON objects")]

    issues: list[ValidationIssue] = []
    for idx, item in enumerate(records):
        issues.extend(validate_bilingual_record(item, idx=idx))
    issues.extend(validate_unique_ids(records))
    return issues


def validate_golden_corpus_alignment(
    records: list[dict[str, object]],
    *,
    published_module_ids: set[str],
    published_card_ids: set[str],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for idx, item in enumerate(records):
        record_id = _record_id(item, idx)
        module_ids = _parse_uuid_list(item.get("module_id"), field="module_id", record_id=record_id) or []
        card_ids = (
            _parse_uuid_list(item.get("source_card_id"), field="source_card_id", record_id=record_id) or []
        )

        for module_id in module_ids:
            if module_id not in published_module_ids:
                issues.append(ValidationIssue(record_id, f"module_id not in published corpus: {module_id}"))
        for card_id in card_ids:
            if card_id not in published_card_ids:
                issues.append(
                    ValidationIssue(record_id, f"source_card_id not in published corpus: {card_id}")
                )
    return issues


def validate_golden_card_module_alignment(
    records: list[dict[str, object]],
    *,
    card_to_module: dict[str, str],
) -> list[ValidationIssue]:
    """Ensure each source_card_id belongs to at least one listed module_id."""
    issues: list[ValidationIssue] = []
    for idx, item in enumerate(records):
        record_id = _record_id(item, idx)
        module_ids = _parse_uuid_list(item.get("module_id"), field="module_id", record_id=record_id) or []
        card_ids = (
            _parse_uuid_list(item.get("source_card_id"), field="source_card_id", record_id=record_id) or []
        )
        module_id_set = set(module_ids)
        for card_id in card_ids:
            owner_module = card_to_module.get(card_id)
            if owner_module is None:
                continue
            if owner_module not in module_id_set:
                issues.append(
                    ValidationIssue(
                        record_id,
                        f"source_card_id {card_id} belongs to module {owner_module}, "
                        f"not listed in module_id {sorted(module_id_set)}",
                    )
                )
    return issues


def load_taxonomy(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}
