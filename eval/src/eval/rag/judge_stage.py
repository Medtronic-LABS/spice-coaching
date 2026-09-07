"""Offline LLM judge stage for generation/eval reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

from platform_service.integrations.ai_runtime_client import AIRuntimeClient

from eval.rag.answer_metrics import aggregate_e2e_summaries
from eval.rag.corpus import CardCorpusDoc
from eval.rag.llm_judge import JudgeInput, LlmJudge
from eval.rag.rag_dataset import Answerable

ReportKind = Literal["rag", "generation"]


def _artifact_query(artifact: dict[str, object]) -> str:
    for key in ("query", "question"):
        value = artifact.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _artifact_answer(artifact: dict[str, object]) -> str:
    value = artifact.get("answer")
    return value if isinstance(value, str) else ""


def _artifact_expected_answer(artifact: dict[str, object]) -> str:
    value = artifact.get("expected_answer")
    return value if isinstance(value, str) else ""


def _artifact_answerable(artifact: dict[str, object]) -> Answerable:
    raw = str(artifact.get("answerable", "yes")).strip().casefold()
    if raw in {"yes", "no", "partial"}:
        return cast(Answerable, raw)
    return "yes"


def _artifact_language(artifact: dict[str, object]) -> str:
    value = artifact.get("language")
    if isinstance(value, str) and value.strip():
        return value.strip()
    value = artifact.get("question_lang")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "bn"


def _artifact_module_ids(artifact: dict[str, object]) -> list[UUID]:
    raw = artifact.get("retrieved_module_ids")
    if not isinstance(raw, list):
        return []
    module_ids: list[UUID] = []
    for item in raw:
        try:
            module_ids.append(UUID(str(item)))
        except (ValueError, TypeError):
            continue
    return module_ids


def judge_input_from_artifact(artifact: dict[str, object]) -> JudgeInput | None:
    answer = _artifact_answer(artifact)
    question = _artifact_query(artifact)
    if not question:
        return None
    context = artifact.get("generation_context")
    generation_context = context if isinstance(context, str) else ""
    return JudgeInput(
        question=question,
        answer=answer,
        expected_answer=_artifact_expected_answer(artifact),
        generation_context=generation_context,
        answerable=_artifact_answerable(artifact),
        is_out_of_scope=bool(artifact.get("is_out_of_scope")),
        category=str(artifact.get("category", "")),
        language=_artifact_language(artifact),
    )


def detect_report_kind(payload: dict[str, object]) -> ReportKind:
    method = str(payload.get("retrieval_method", "")).strip().casefold()
    if method in {"bm25", "embedding"}:
        return "generation"
    return "rag"


def load_report_payload(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: report root must be a JSON object")
    artifacts = raw.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError(f"{path}: report missing artifacts array")
    return raw


def judgeable_artifact_count(artifacts: list[dict[str, object]]) -> int:
    count = 0
    for artifact in artifacts:
        if judge_input_from_artifact(artifact) is not None and _artifact_answer(artifact).strip():
            count += 1
    return count


async def run_judge_stage(
    artifacts: list[dict[str, object]],
    *,
    judge: LlmJudge,
    cards_by_module: dict[UUID, list[CardCorpusDoc]] | None = None,
) -> list[dict[str, object]]:
    cards = cards_by_module or {}
    judged: list[dict[str, object]] = []
    for artifact in artifacts:
        updated = dict(artifact)
        judge_input = judge_input_from_artifact(updated)
        if judge_input is None:
            updated["judge_metrics"] = {
                "judge_error": "missing query/question on artifact",
            }
            judged.append(updated)
            continue

        if not judge_input.answer.strip():
            updated["judge_metrics"] = {
                "judge_error": "empty answer",
            }
            judged.append(updated)
            continue

        if judge_input.generation_context.strip():
            scores = await judge.score(judge_input)
        else:
            scores = await judge.score_with_fallback_context(
                question=judge_input.question,
                answer=judge_input.answer,
                expected_answer=judge_input.expected_answer,
                answerable=judge_input.answerable,
                is_out_of_scope=judge_input.is_out_of_scope,
                category=judge_input.category,
                language=judge_input.language,
                generation_context=None,
                retrieved_module_ids=_artifact_module_ids(updated),
                cards_by_module=cards,
            )
        updated["judge_metrics"] = scores.as_dict()
        judged.append(updated)
    return judged


def merge_judge_summary(
    report: dict[str, object], judged_artifacts: list[dict[str, object]]
) -> dict[str, object]:
    kind = detect_report_kind(report)
    if kind == "rag":
        raw_e2e = report.get("e2e_summary")
        e2e_summary: dict[str, object] = dict(raw_e2e) if isinstance(raw_e2e, dict) else {}
        e2e_summary["judge_summary"] = aggregate_e2e_summaries(judged_artifacts).get("judge_summary", {})
        report["e2e_summary"] = e2e_summary
        report["judge_summary"] = e2e_summary["judge_summary"]
        return report

    judge_summary = aggregate_e2e_summaries(judged_artifacts).get("judge_summary", {})
    report["judge_summary"] = judge_summary
    return report


async def judge_report_file(
    input_path: Path,
    *,
    client: AIRuntimeClient,
    cards_by_module: dict[UUID, list[CardCorpusDoc]] | None = None,
) -> dict[str, object]:
    report = load_report_payload(input_path)
    artifacts_raw = report.get("artifacts")
    assert isinstance(artifacts_raw, list)
    artifacts = [dict(item) for item in artifacts_raw if isinstance(item, dict)]
    judge = LlmJudge(client)
    judged = await run_judge_stage(artifacts, judge=judge, cards_by_module=cards_by_module)
    report["artifacts"] = judged
    return merge_judge_summary(report, judged)


def write_report_payload(report: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
