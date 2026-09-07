"""Unit tests for LLM-driven golden dataset expansion."""

from __future__ import annotations

import json
from itertools import cycle
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from eval.rag.golden_expansion import (
    build_generation_plan,
    collect_domain_expansion_prompts,
    compute_next_record_id_for_ingest,
    group_response_files_by_domain,
    infer_domain_from_response_path,
    ingest_expansion_responses,
    ingest_manual_expansion_response,
    load_taxonomy,
    normalize_and_validate_records,
    normalize_query_type,
    parse_llm_records,
    parse_manual_response_payload,
    pilot_module_counts,
    select_pilot_examples,
    shard_for_domain,
    write_domain_expansion_shard,
    write_domain_prompt_exports,
    write_expansion_shards_from_domains,
)
from eval.rag.golden_expansion_templates import target_records_for_module
from eval.rag.golden_schema import validate_bilingual_record
from mc_contracts.enums import GenerationType
from mc_contracts.internal_ai import InferenceResponse, TokenUsage

from eval.rag import golden_expansion as ge

MODULE_A = "11111111-1111-1111-1111-111111111111"
MODULE_B = "22222222-2222-2222-2222-222222222222"
CARD_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CARD_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def test_shard_for_domain() -> None:
    assert shard_for_domain("anc") == "anc.json"
    assert shard_for_domain("malaria") == "infectious.json"
    assert shard_for_domain("unknown") == "anc.json"


def _pilot_record(
    record_id: str,
    *,
    answerable: str = "yes",
    module_id: str | None = MODULE_A,
) -> dict[str, object]:
    return {
        "id": record_id,
        "question_en": f"Question {record_id}?",
        "question_bn": f"প্রশ্ন {record_id}?",
        "expected_answer_en": "Answer.",
        "expected_answer_bn": "উত্তর।",
        "module_id": [module_id] if module_id else [],
        "source_card_id": [CARD_A] if module_id else [],
        "query_type": "Scenario-based",
        "answerable": answerable,
        "confidence": "high",
    }


def test_select_pilot_examples_prefers_shard_local() -> None:
    pilots = [
        _pilot_record("Q001"),
        _pilot_record("Q002"),
        _pilot_record("Q015"),
    ]
    examples = select_pilot_examples("anc.json", pilots, max_examples=5)
    assert len(examples) == 2
    assert {str(record["id"]) for record in examples} == {"Q001", "Q002"}


def test_select_pilot_examples_global_fallback() -> None:
    pilots = [
        _pilot_record("Q001"),
        _pilot_record("Q002"),
        _pilot_record("Q003"),
        _pilot_record("Q015"),
        _pilot_record("Q016"),
        _pilot_record("Q023"),
    ]
    examples = select_pilot_examples("infectious.json", pilots, max_examples=3)
    assert len(examples) == 3
    assert {str(record["id"]) for record in examples} <= {"Q001", "Q002", "Q003", "Q015", "Q016", "Q023"}


def test_pilot_module_counts_skips_negative() -> None:
    pilots = [
        _pilot_record("Q001", module_id=MODULE_A),
        _pilot_record("Q004", answerable="no", module_id=None),
    ]
    counts = pilot_module_counts(pilots)
    assert counts == {MODULE_A: 1}


def test_target_records_for_module() -> None:
    assert target_records_for_module(2) == 4
    assert target_records_for_module(5) == 6
    assert target_records_for_module(10) == 12


def test_build_generation_plan_respects_pilot_coverage() -> None:
    module = MagicMock()
    module.id = UUID(MODULE_A)
    module.title_localized = {"bn": "টেস্ট মডিউল"}
    cards_by_module = {
        module.id: [
            {"id": CARD_A, "card_order": 1, "title_localized": {"bn": "কার্ড"}},
            {"id": CARD_B, "card_order": 2, "title_localized": {"bn": "কার্ড ২"}},
            {"id": "cccccccc-cccc-cccc-cccc-cccccccccccc", "card_order": 3},
            {"id": "dddddddd-dddd-dddd-dddd-dddddddddddd", "card_order": 4},
        ]
    }
    pilot_counts = {MODULE_A: 2}
    tasks = build_generation_plan([module], cards_by_module, pilot_counts)
    assert len(tasks) == 1
    assert tasks[0].needed_count == 4
    assert tasks[0].module_id == MODULE_A
    assert len(tasks[0].query_types) == 4


def test_normalize_query_type_aliases() -> None:
    taxonomy = load_taxonomy()
    assert normalize_query_type("Scenario-based", taxonomy) == "Situational"
    assert normalize_query_type("Factual", taxonomy) == "Factual"


def test_parse_llm_records() -> None:
    assert parse_llm_records({"records": [{"question_en": "x"}]}) == [{"question_en": "x"}]
    assert parse_llm_records([{"question_en": "x"}]) == [{"question_en": "x"}]
    assert parse_llm_records({"other": []}) == []


def test_normalize_and_validate_records_accepts_valid_row() -> None:
    taxonomy = load_taxonomy()
    raw = [
        {
            "question_en": "What should I do?",
            "question_bn": "আমি কী করব?",
            "expected_answer_en": "Refer immediately.",
            "expected_answer_bn": "তাৎক্ষণিক রেফার করুন।",
            "module_id": [MODULE_A],
            "source_card_id": [CARD_A],
            "query_type": "Scenario-based",
            "chw_pattern": "Referral & Escalation",
            "answerable": "yes",
            "confidence": "high",
        }
    ]
    accepted, next_id = normalize_and_validate_records(
        raw,
        valid_module_ids={MODULE_A},
        valid_card_ids={CARD_A, CARD_B},
        card_to_module={CARD_A: MODULE_A, CARD_B: MODULE_A},
        taxonomy=taxonomy,
        linguistic_cycle=cycle(["Standard Written Bengali"]),
        start_id=26,
    )
    assert len(accepted) == 1
    assert accepted[0]["id"] == "Q026"
    assert accepted[0]["query_type"] == "Situational"
    assert not validate_bilingual_record(accepted[0], idx=0)


def test_normalize_and_validate_records_rejects_bad_uuids() -> None:
    taxonomy = load_taxonomy()
    raw = [
        {
            "question_en": "What?",
            "question_bn": "কী?",
            "expected_answer_en": "Answer.",
            "expected_answer_bn": "উত্তর।",
            "module_id": ["00000000-0000-0000-0000-000000000099"],
            "source_card_id": [CARD_A],
            "query_type": "Factual",
            "answerable": "yes",
        }
    ]
    accepted, next_id = normalize_and_validate_records(
        raw,
        valid_module_ids={MODULE_A},
        valid_card_ids={CARD_A},
        card_to_module={CARD_A: MODULE_A},
        taxonomy=taxonomy,
        linguistic_cycle=cycle(["Standard Written Bengali"]),
        start_id=26,
    )
    assert accepted == []
    assert next_id == 26


@pytest.mark.asyncio
async def test_generate_expansion_shards_template_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    module = MagicMock()
    module.id = UUID(MODULE_A)
    module.domain = "anc"
    module.title_localized = {"bn": "টেস্ট"}

    async def fake_load_modules(*, tenant_id: int | None = None) -> list[MagicMock]:
        return [module]

    async def fake_load_cards(module_ids: list[UUID]) -> dict[UUID, list[dict[str, object]]]:
        return {
            module.id: [
                {
                    "id": CARD_A,
                    "card_order": 1,
                    "title_localized": {"bn": "শিরোনাম", "en": "Title"},
                    "body_localized": {"bn": "বিস্তারিত তথ্য।", "en": "Details."},
                }
            ]
        }

    monkeypatch.setattr(ge, "load_published_modules", fake_load_modules)
    monkeypatch.setattr(ge, "load_cards_by_module_ids", fake_load_cards)
    monkeypatch.setattr(ge, "load_pilot_records", lambda path=ge.PILOT_PATH: [])

    shards = await ge.generate_expansion_shards(template_fallback=True, domain_filter="anc")
    assert "anc.json" in shards
    generated = [record for record in shards["anc.json"] if str(record.get("id", "")).startswith("Q")]
    assert generated
    assert all(record.get("answerable") == "yes" for record in generated)
    assert not validate_bilingual_record(generated[0], idx=0)


@pytest.mark.asyncio
async def test_generate_expansion_shards_mocked_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    module = MagicMock()
    module.id = UUID(MODULE_A)
    module.domain = "anc"
    module.title_localized = {"bn": "টেস্ট"}

    async def fake_load_modules(*, tenant_id: int | None = None) -> list[MagicMock]:
        return [module]

    async def fake_load_cards(module_ids: list[UUID]) -> dict[UUID, list[dict[str, object]]]:
        return {
            module.id: [
                {
                    "id": CARD_A,
                    "card_order": 1,
                    "title_localized": {"bn": "শিরোনাম"},
                    "body_localized": {"bn": "বিস্তারিত তথ্য।"},
                },
                {
                    "id": CARD_B,
                    "card_order": 2,
                    "title_localized": {"bn": "দ্বিতীয়"},
                    "body_localized": {"bn": "আরও তথ্য।"},
                },
                {
                    "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                    "card_order": 3,
                    "title_localized": {"bn": "তৃতীয়"},
                    "body_localized": {"bn": "তথ্য ৩।"},
                },
                {
                    "id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
                    "card_order": 4,
                    "title_localized": {"bn": "চতুর্থ"},
                    "body_localized": {"bn": "তথ্য ৪।"},
                },
            ]
        }

    llm_record = {
        "question_en": "During a visit I see edema — what next?",
        "question_bn": "ভিজিটে ইডিমা দেখলাম — পরবর্তী কী?",
        "expected_answer_en": "Check blood pressure and refer if high.",
        "expected_answer_bn": "রক্তচাপ পরীক্ষা করুন এবং বেশি হলে রেফার করুন।",
        "module_id": [MODULE_A],
        "source_card_id": [CARD_A],
        "query_type": "Situational",
        "chw_pattern": "Clinical Protocol & Escalation",
        "answerable": "yes",
        "confidence": "high",
        "linguistic_variation": "Standard Written Bengali",
    }

    mock_client = MagicMock()
    mock_client.generate = AsyncMock(
        return_value=InferenceResponse(
            request_id="req-1",
            generation_type=GenerationType.GOLDEN_EXPANSION,
            provider="google",
            model="test-model",
            max_tokens=8192,
            temperature=0.2,
            raw_text="",
            parsed_json={"records": [llm_record]},
            latency_ms=10,
            token_usage=TokenUsage(input=1, output=1),
            error=None,
        )
    )

    monkeypatch.setattr(ge, "load_published_modules", fake_load_modules)
    monkeypatch.setattr(ge, "load_cards_by_module_ids", fake_load_cards)
    monkeypatch.setattr(ge, "load_pilot_records", lambda path=ge.PILOT_PATH: [])
    monkeypatch.setattr(ge, "compute_next_record_id_for_ingest", lambda shard_name, **kwargs: 1)

    shards = await ge.generate_expansion_shards(
        client=mock_client,
        template_fallback=False,
        domain_filter="anc",
    )
    assert mock_client.generate.await_count >= 1
    llm_generated = [
        record for record in shards["anc.json"] if record.get("question_en") == llm_record["question_en"]
    ]
    assert len(llm_generated) == 1
    assert llm_generated[0]["id"] == "Q001"
    assert not validate_bilingual_record(llm_generated[0], idx=0)


def _mock_module(*, domain: str = "anc") -> MagicMock:
    module = MagicMock()
    module.id = UUID(MODULE_A)
    module.domain = domain
    module.title_localized = {"bn": "টেস্ট"}
    return module


def _four_card_corpus(module: MagicMock) -> dict[UUID, list[dict[str, object]]]:
    return {
        module.id: [
            {
                "id": CARD_A,
                "card_order": 1,
                "title_localized": {"bn": "শিরোনাম"},
                "body_localized": {"bn": "বিস্তারিত তথ্য।"},
            },
            {
                "id": CARD_B,
                "card_order": 2,
                "title_localized": {"bn": "দ্বিতীয়"},
                "body_localized": {"bn": "আরও তথ্য।"},
            },
            {
                "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "card_order": 3,
                "title_localized": {"bn": "তৃতীয়"},
                "body_localized": {"bn": "তথ্য ৩।"},
            },
            {
                "id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
                "card_order": 4,
                "title_localized": {"bn": "চতুর্থ"},
                "body_localized": {"bn": "তথ্য ৪।"},
            },
        ]
    }


def test_collect_domain_expansion_prompts_returns_batches() -> None:
    module = _mock_module()
    cards_by_module = _four_card_corpus(module)
    taxonomy = load_taxonomy()
    batches = collect_domain_expansion_prompts(
        domain="anc",
        domain_modules=[module],
        cards_by_module=cards_by_module,
        pilot_records=[],
        pilot_counts={},
        taxonomy=taxonomy,
    )
    assert len(batches) == 1
    assert batches[0].domain == "anc"
    assert batches[0].batch_index == 0
    assert batches[0].batch_count == 1
    assert batches[0].expected_record_count == 6
    assert batches[0].system_prompt
    assert "DOMAIN: anc" in batches[0].human_message


def test_write_domain_prompt_exports_writes_json_and_md(tmp_path: Path) -> None:
    module = _mock_module()
    cards_by_module = _four_card_corpus(module)
    taxonomy = load_taxonomy()
    batches = collect_domain_expansion_prompts(
        domain="anc",
        domain_modules=[module],
        cards_by_module=cards_by_module,
        pilot_records=[],
        pilot_counts={},
        taxonomy=taxonomy,
    )
    written = write_domain_prompt_exports(batches, tmp_path)
    assert (tmp_path / "anc_batch0.prompt.json").exists()
    assert (tmp_path / "anc_batch0.prompt.md").exists()
    assert (tmp_path / "anc_manifest.json").exists()

    payload = json.loads((tmp_path / "anc_batch0.prompt.json").read_text(encoding="utf-8"))
    assert payload["domain"] == "anc"
    assert payload["system_prompt"]
    assert payload["human_message"]
    md_text = (tmp_path / "anc_batch0.prompt.md").read_text(encoding="utf-8")
    assert "## System" in md_text
    assert "## Human" in md_text
    assert len(written) == 3


def test_parse_manual_response_payload_strips_markdown_fences() -> None:
    payload = parse_manual_response_payload('```json\n{"records": [{"question_en": "x"}]}\n```')
    assert payload == {"records": [{"question_en": "x"}]}


def test_infer_domain_from_response_path() -> None:
    assert infer_domain_from_response_path(Path("anc_batch0.response.json")) == "anc"
    assert infer_domain_from_response_path(Path("diarrhea_batch2.response.json")) == "diarrhea"
    assert infer_domain_from_response_path(Path("anc_batch0.json")) == "anc"
    assert infer_domain_from_response_path(Path("invalid.json")) is None


def test_group_response_files_by_domain(tmp_path: Path) -> None:
    (tmp_path / "anc_batch0.response.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pnc_batch0.response.json").write_text("{}", encoding="utf-8")
    (tmp_path / "anc_manifest.json").write_text("{}", encoding="utf-8")

    grouped = group_response_files_by_domain(
        tmp_path,
        {"anc", "pnc"},
    )
    assert set(grouped.keys()) == {"anc", "pnc"}
    assert len(grouped["anc"]) == 1

    filtered = group_response_files_by_domain(
        tmp_path,
        {"anc", "pnc"},
        domain_filter="anc",
    )
    assert set(filtered.keys()) == {"anc"}


def test_compute_next_record_id_for_ingest_excludes_replaced_shard(
    tmp_path: Path,
) -> None:
    records_dir = tmp_path / "records"
    records_dir.mkdir()
    (records_dir / "anc.json").write_text(
        json.dumps(
            [
                {"id": "Q001"},
                {"id": "Q026"},
                {"id": "Q027"},
            ]
        ),
        encoding="utf-8",
    )
    (records_dir / "pnc.json").write_text(json.dumps([{"id": "Q050"}]), encoding="utf-8")

    next_id = compute_next_record_id_for_ingest(
        "anc.json",
        pilot_records=[{"id": "Q001"}],
        records_dir=records_dir,
    )
    assert next_id == 51


def test_write_domain_expansion_shard_preserves_pilots(tmp_path: Path) -> None:
    pilots = [_pilot_record("Q001"), _pilot_record("Q002")]
    expansion = [
        {
            "id": "Q026",
            "question_en": "Q?",
            "question_bn": "প?",
            "expected_answer_en": "A.",
            "expected_answer_bn": "উ.",
            "module_id": [MODULE_A],
            "source_card_id": [CARD_A],
            "query_type": "Factual",
            "answerable": "yes",
            "confidence": "high",
        }
    ]
    path = write_domain_expansion_shard(
        domain="anc",
        expansion_records=expansion,
        pilot_records=pilots,
        records_dir=tmp_path,
    )
    written = json.loads(path.read_text(encoding="utf-8"))
    assert len(written) == 3
    assert written[0]["id"] == "Q001"
    assert written[-1]["id"] == "Q026"


@pytest.mark.asyncio
async def test_ingest_manual_expansion_response_accepts_valid_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _mock_module()
    cards_by_module = _four_card_corpus(module)

    async def fake_load_modules(*, tenant_id: int | None = None) -> list[MagicMock]:
        return [module]

    async def fake_load_cards(module_ids: list[UUID]) -> dict[UUID, list[dict[str, object]]]:
        return cards_by_module

    monkeypatch.setattr(ge, "load_published_modules", fake_load_modules)
    monkeypatch.setattr(ge, "load_cards_by_module_ids", fake_load_cards)
    monkeypatch.setattr(ge, "load_pilot_records", lambda path=ge.PILOT_PATH: [])
    monkeypatch.setattr(
        ge,
        "compute_next_record_id_for_ingest",
        lambda *args, **kwargs: 26,
    )

    response_path = tmp_path / "anc_batch0.response.json"
    response_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "question_en": "Manual question?",
                        "question_bn": "ম্যানুয়াল প্রশ্ন?",
                        "expected_answer_en": "Manual answer.",
                        "expected_answer_bn": "ম্যানুয়াল উত্তর।",
                        "module_id": [MODULE_A],
                        "source_card_id": [CARD_A],
                        "query_type": "Factual",
                        "chw_pattern": "Referral & Escalation",
                        "answerable": "yes",
                        "confidence": "high",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    accepted = await ingest_manual_expansion_response(
        domain="anc",
        response_path=response_path,
    )
    assert len(accepted) == 1
    assert accepted[0]["id"] == "Q026"
    assert accepted[0]["question_en"] == "Manual question?"


@pytest.mark.asyncio
async def test_ingest_manual_expansion_response_rejects_bad_uuids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _mock_module()
    cards_by_module = _four_card_corpus(module)

    async def fake_load_modules(*, tenant_id: int | None = None) -> list[MagicMock]:
        return [module]

    async def fake_load_cards(module_ids: list[UUID]) -> dict[UUID, list[dict[str, object]]]:
        return cards_by_module

    monkeypatch.setattr(ge, "load_published_modules", fake_load_modules)
    monkeypatch.setattr(ge, "load_cards_by_module_ids", fake_load_cards)
    monkeypatch.setattr(ge, "load_pilot_records", lambda path=ge.PILOT_PATH: [])

    response_path = tmp_path / "anc_batch0.response.json"
    response_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "question_en": "Bad?",
                        "question_bn": "খারাপ?",
                        "expected_answer_en": "No.",
                        "expected_answer_bn": "না।",
                        "module_id": ["00000000-0000-0000-0000-000000000099"],
                        "source_card_id": [CARD_A],
                        "query_type": "Factual",
                        "answerable": "yes",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    accepted = await ingest_manual_expansion_response(
        domain="anc",
        response_path=response_path,
    )
    assert accepted == []


@pytest.mark.asyncio
async def test_ingest_manual_expansion_response_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _mock_module()
    cards_by_module = _four_card_corpus(module)

    async def fake_load_modules(*, tenant_id: int | None = None) -> list[MagicMock]:
        return [module]

    async def fake_load_cards(module_ids: list[UUID]) -> dict[UUID, list[dict[str, object]]]:
        return cards_by_module

    monkeypatch.setattr(ge, "load_published_modules", fake_load_modules)
    monkeypatch.setattr(ge, "load_cards_by_module_ids", fake_load_cards)
    monkeypatch.setattr(ge, "load_pilot_records", lambda path=ge.PILOT_PATH: [])
    monkeypatch.setattr(
        ge,
        "compute_next_record_id_for_ingest",
        lambda *args, **kwargs: 26,
    )

    record_template = {
        "question_bn": "প?",
        "expected_answer_en": "A.",
        "expected_answer_bn": "উ.",
        "module_id": [MODULE_A],
        "source_card_id": [CARD_A],
        "query_type": "Factual",
        "chw_pattern": "Referral & Escalation",
        "answerable": "yes",
        "confidence": "high",
    }
    (tmp_path / "anc_batch0.response.json").write_text(
        json.dumps({"records": [{**record_template, "question_en": "First?"}]}),
        encoding="utf-8",
    )
    (tmp_path / "anc_batch1.response.json").write_text(
        json.dumps({"records": [{**record_template, "question_en": "Second?"}]}),
        encoding="utf-8",
    )

    accepted = await ingest_manual_expansion_response(
        domain="anc",
        response_path=tmp_path,
    )
    assert len(accepted) == 2
    assert accepted[0]["id"] == "Q026"
    assert accepted[1]["id"] == "Q027"


@pytest.mark.asyncio
async def test_generate_expansion_shards_domain_filter_returns_single_shard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _mock_module(domain="anc")

    async def fake_load_modules(*, tenant_id: int | None = None) -> list[MagicMock]:
        return [module]

    async def fake_load_cards(module_ids: list[UUID]) -> dict[UUID, list[dict[str, object]]]:
        return _four_card_corpus(module)

    monkeypatch.setattr(ge, "load_published_modules", fake_load_modules)
    monkeypatch.setattr(ge, "load_cards_by_module_ids", fake_load_cards)
    monkeypatch.setattr(ge, "load_pilot_records", lambda path=ge.PILOT_PATH: [])

    shards = await ge.generate_expansion_shards(template_fallback=True, domain_filter="anc")
    assert set(shards.keys()) == {"anc.json"}


@pytest.mark.asyncio
async def test_export_expansion_prompts_all_domains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anc_module = _mock_module(domain="anc")
    pnc_module = _mock_module(domain="pnc")
    pnc_module.id = UUID(MODULE_B)

    async def fake_load_corpus(*, tenant_id: int | None = None):
        modules = [anc_module, pnc_module]
        cards_by_module = {
            **_four_card_corpus(anc_module),
            **_four_card_corpus(pnc_module),
        }
        modules_by_domain = {"anc": [anc_module], "pnc": [pnc_module]}
        return modules, cards_by_module, modules_by_domain

    monkeypatch.setattr(ge, "_load_expansion_corpus", fake_load_corpus)
    monkeypatch.setattr(ge, "load_pilot_records", lambda path=ge.PILOT_PATH: [])

    written = await ge.export_expansion_prompts(output_dir=tmp_path)
    assert (tmp_path / "anc_manifest.json").exists()
    assert (tmp_path / "pnc_manifest.json").exists()
    assert any(path.name.startswith("anc_batch") for path in written)
    assert any(path.name.startswith("pnc_batch") for path in written)


@pytest.mark.asyncio
async def test_ingest_expansion_responses_all_domains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anc_module = _mock_module(domain="anc")
    pnc_module = _mock_module(domain="pnc")
    pnc_module.id = UUID(MODULE_B)

    async def fake_load_corpus(*, tenant_id: int | None = None):
        modules = [anc_module, pnc_module]
        cards_by_module = {
            **_four_card_corpus(anc_module),
            **_four_card_corpus(pnc_module),
        }
        modules_by_domain = {"anc": [anc_module], "pnc": [pnc_module]}
        return modules, cards_by_module, modules_by_domain

    monkeypatch.setattr(ge, "_load_expansion_corpus", fake_load_corpus)
    monkeypatch.setattr(ge, "load_pilot_records", lambda path=ge.PILOT_PATH: [])
    monkeypatch.setattr(
        ge,
        "compute_next_record_id_for_ingest",
        lambda *args, **kwargs: 26,
    )

    record_template = {
        "question_bn": "প?",
        "expected_answer_en": "A.",
        "expected_answer_bn": "উ.",
        "query_type": "Factual",
        "chw_pattern": "Referral & Escalation",
        "answerable": "yes",
        "confidence": "high",
    }
    (tmp_path / "anc_batch0.response.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        **record_template,
                        "question_en": "ANC question?",
                        "module_id": [MODULE_A],
                        "source_card_id": [CARD_A],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnc_batch0.response.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        **record_template,
                        "question_en": "PNC question?",
                        "module_id": [MODULE_B],
                        "source_card_id": [CARD_A],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    by_domain = await ingest_expansion_responses(response_path=tmp_path)
    assert set(by_domain.keys()) == {"anc", "pnc"}
    assert by_domain["anc"][0]["question_en"] == "ANC question?"
    assert by_domain["pnc"][0]["question_en"] == "PNC question?"
    assert by_domain["anc"][0]["id"] == "Q026"
    assert by_domain["pnc"][0]["id"] == "Q027"


def test_write_expansion_shards_from_domains_merges_shared_shards(tmp_path: Path) -> None:
    record_template = {
        "id": "Q026",
        "question_bn": "প?",
        "expected_answer_en": "A.",
        "expected_answer_bn": "উ.",
        "query_type": "Factual",
        "chw_pattern": "Referral & Escalation",
        "answerable": "yes",
        "confidence": "high",
    }
    written = write_expansion_shards_from_domains(
        records_by_domain={
            "malaria": [
                {
                    **record_template,
                    "id": "Q026",
                    "question_en": "Malaria question?",
                    "module_id": [MODULE_A],
                    "source_card_id": [CARD_A],
                }
            ],
            "dengue": [
                {
                    **record_template,
                    "id": "Q027",
                    "question_en": "Dengue question?",
                    "module_id": [MODULE_A],
                    "source_card_id": [CARD_A],
                }
            ],
        },
        pilot_records=[],
        records_dir=tmp_path,
    )

    assert set(written.keys()) == {"infectious.json"}
    merged = json.loads((tmp_path / "infectious.json").read_text(encoding="utf-8"))
    assert len(merged) == 2
    assert merged[0]["question_en"] == "Malaria question?"
    assert merged[1]["question_en"] == "Dengue question?"
