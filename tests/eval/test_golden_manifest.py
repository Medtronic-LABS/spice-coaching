"""Tests for golden manifest loading, validation, and coverage."""

from __future__ import annotations

import json
from pathlib import Path

from eval.rag.dataset import load_golden_dataset
from eval.rag.golden_manifest import compile_manifest, load_golden_source_array, load_manifest_records
from eval.rag.golden_schema import (
    validate_bilingual_record,
    validate_golden_card_module_alignment,
    validate_golden_dataset,
    validate_unique_ids,
)


def test_manifest_merge_loader(tmp_path: Path) -> None:
    shard_a = tmp_path / "a.json"
    shard_b = tmp_path / "b.json"
    shard_a.write_text(
        json.dumps(
            [
                {
                    "id": "Q001",
                    "question_en": "What is hypertension?",
                    "question_bn": "উচ্চ রক্তচাপ কী?",
                    "expected_answer_en": "High blood pressure.",
                    "expected_answer_bn": "উচ্চ রক্তচাপ।",
                    "module_id": [],
                    "source_card_id": [],
                    "query_type": "Negative",
                    "answerable": "no",
                }
            ]
        ),
        encoding="utf-8",
    )
    shard_b.write_text(
        json.dumps(
            [
                {
                    "id": "Q002",
                    "question_en": "ANC visit?",
                    "question_bn": "এএনসি?",
                    "expected_answer_en": "Regular visits.",
                    "expected_answer_bn": "নিয়মিত ভিজিট।",
                    "module_id": ["4422af94-662c-4a84-9c54-68dc4cf6888d"],
                    "source_card_id": ["aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"],
                    "query_type": "Factual",
                    "answerable": "yes",
                }
            ]
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "test.manifest.json"
    manifest.write_text(
        json.dumps({"compiled_output": "compiled.json", "records": ["a.json", "b.json"]}),
        encoding="utf-8",
    )

    records = load_manifest_records(manifest)
    assert len(records) == 2
    assert records[0]["id"] == "Q001"
    assert records[1]["id"] == "Q002"


def test_validate_bilingual_record_rejects_inconsistent_answerable() -> None:
    issues = validate_bilingual_record(
        {
            "id": "Q999",
            "question_en": "Q",
            "question_bn": "প্র",
            "expected_answer_en": "A",
            "expected_answer_bn": "উ",
            "module_id": ["4422af94-662c-4a84-9c54-68dc4cf6888d"],
            "source_card_id": [],
            "query_type": "Factual",
            "answerable": "no",
        },
        idx=0,
    )
    assert any("answerable=no requires empty module_id" in issue.message for issue in issues)


def test_validate_unique_ids_detects_duplicates() -> None:
    records = [{"id": "Q001"}, {"id": "Q001"}]
    issues = validate_unique_ids(records)
    assert len(issues) == 1


def test_validate_card_module_alignment_rejects_mismatched_card() -> None:
    module_a = "1d030fd0-6541-4e4b-bb0b-38a1cc2b29ab"
    module_b = "3f751ce8-c5fc-4a45-9bd2-6f7c4807e396"
    card_id = "dbef5a4b-e803-41b4-93af-cd4e6dbde2ff"
    records = [
        {
            "id": "Q230",
            "module_id": [module_b],
            "source_card_id": [card_id],
        }
    ]
    issues = validate_golden_card_module_alignment(records, card_to_module={card_id: module_a})
    assert len(issues) == 1
    assert "not listed in module_id" in issues[0].message


def test_validate_card_module_alignment_accepts_matching_card() -> None:
    module_a = "1d030fd0-6541-4e4b-bb0b-38a1cc2b29ab"
    card_id = "dbef5a4b-e803-41b4-93af-cd4e6dbde2ff"
    records = [
        {
            "id": "Q230",
            "module_id": [module_a],
            "source_card_id": [card_id],
        }
    ]
    issues = validate_golden_card_module_alignment(records, card_to_module={card_id: module_a})
    assert issues == []


def test_golden_compile_round_trip(tmp_path: Path) -> None:
    shard = tmp_path / "records.json"
    shard.write_text(
        json.dumps(
            [
                {
                    "id": "Q001",
                    "question_en": "Q",
                    "question_bn": "প্র",
                    "expected_answer_en": "A",
                    "expected_answer_bn": "উ",
                    "module_id": [],
                    "source_card_id": [],
                    "query_type": "Negative",
                    "answerable": "no",
                }
            ]
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "set.manifest.json"
    manifest.write_text(
        json.dumps({"compiled_output": "compiled.json", "records": ["records.json"]}),
        encoding="utf-8",
    )
    output = compile_manifest(manifest)
    compiled = json.loads(output.read_text(encoding="utf-8"))
    assert len(compiled) == 1
    assert compiled[0]["id"] == "Q001"


def test_production_manifest_passes_schema_validation() -> None:
    path = Path("eval/rag/golden/Golden_Dataset.manifest.json")
    issues = validate_golden_dataset(path)
    assert issues == []


def test_production_manifest_loads_bilingual_records() -> None:
    records = load_golden_source_array(Path("eval/rag/golden/Golden_Dataset.manifest.json"))
    assert len(records) == 249
    bn_records = load_golden_dataset(Path("eval/rag/golden/Golden_Dataset.manifest.json"), language="bn")
    assert len(bn_records) == 249
    assert bn_records[0].question_lang == "bn"
