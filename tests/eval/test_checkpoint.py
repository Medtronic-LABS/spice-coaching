"""Tests for eval batch checkpoint save/load and resume."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from eval.rag.checkpoint import (
    CHECKPOINT_VERSION,
    CheckpointContext,
    CorpusCounts,
    EvalRunConfig,
    EvalRunProgress,
    SkipKind,
    after_record,
    checkpoint_path,
    delete_checkpoint,
    ensure_resume_policy,
    init_progress,
    load_checkpoint,
    write_checkpoint,
)
from eval.rag.report import RecordArtifact


def _sample_config(**overrides: object) -> EvalRunConfig:
    defaults: dict[str, object] = {
        "method": "bm25",
        "dataset_path": "eval/rag/golden/golden_dataset.json",
        "k": 5,
        "language": "bn",
        "tenant_id": None,
        "generate": False,
        "local_card": False,
        "llm_judge": False,
    }
    defaults.update(overrides)
    return EvalRunConfig(**defaults)  # type: ignore[arg-type]


def _sample_retrieval_artifact(record_id: str = "anc-001") -> RecordArtifact:
    return RecordArtifact(
        id=record_id,
        category="anc",
        question="test question",
        expected_module="module-a",
        relevant_module_ids=["00000000-0000-4000-8000-000000000001"],
        is_answerable=True,
        retrieved_module_ids=["00000000-0000-4000-8000-000000000001"],
        retrieval_scores=[0.5],
        retrieval_metrics={
            "hit_at_k": 1.0,
            "mrr": 1.0,
            "precision_at_k": 0.2,
            "recall_at_k": 1.0,
            "ndcg_at_k": 1.0,
        },
    )


def _sample_dict_artifact(record_id: str = "anc-001") -> dict[str, object]:
    return {
        "id": record_id,
        "category": "anc",
        "query": "test question",
        "answer": "test answer",
        "expected_answer": "expected",
    }


def test_checkpoint_path_names_sibling_file() -> None:
    output = Path("eval/rag/reports/rag-run.json")
    assert checkpoint_path(output) == Path("eval/rag/reports/rag-run-checkpoint.json")


def test_retrieval_checkpoint_round_trip(tmp_path: Path) -> None:
    config = _sample_config()
    progress = EvalRunProgress(run_id="bm25-test", artifact_kind="retrieval")
    progress.mark_evaluated("anc-001", _sample_retrieval_artifact())
    progress.mark_skipped("anc-002", SkipKind.UNANSWERABLE)

    checkpoint_file = tmp_path / "bm25-run-checkpoint.json"
    corpus_counts = CorpusCounts(published=100, embedded=None)
    write_checkpoint(progress, checkpoint_file, config=config, corpus_counts=corpus_counts)

    loaded = load_checkpoint(checkpoint_file, config)
    assert loaded.run_id == "bm25-test"
    assert loaded.records_processed == 2
    assert loaded.skipped_unanswerable_count == 1
    assert loaded.completed_record_ids == {"anc-001", "anc-002"}
    assert len(loaded.retrieval_artifacts()) == 1
    assert loaded.retrieval_artifacts()[0].id == "anc-001"


def test_dict_checkpoint_round_trip(tmp_path: Path) -> None:
    config = _sample_config(method="rag")
    progress = EvalRunProgress(run_id="rag-test", artifact_kind="dict")
    progress.mark_evaluated("anc-001", _sample_dict_artifact())

    checkpoint_file = tmp_path / "rag-run-checkpoint.json"
    corpus_counts = CorpusCounts(published=50, embedded=48)
    write_checkpoint(progress, checkpoint_file, config=config, corpus_counts=corpus_counts)

    loaded = load_checkpoint(checkpoint_file, config)
    assert loaded.dict_artifacts()[0]["id"] == "anc-001"


def test_records_processed_increments_on_evaluate_and_skip() -> None:
    progress = EvalRunProgress(run_id="test", artifact_kind="retrieval")
    progress.mark_evaluated("r1", _sample_retrieval_artifact("r1"))
    progress.mark_skipped("r2", SkipKind.UNANSWERABLE)
    progress.mark_skipped("r3", SkipKind.UNRESOLVABLE)
    assert progress.records_processed == 3


def test_maybe_checkpoint_writes_at_interval(tmp_path: Path) -> None:
    output = tmp_path / "run.json"
    config = _sample_config()
    corpus_counts = CorpusCounts(published=10, embedded=10)
    checkpoint_ctx = CheckpointContext(
        output_path=output,
        interval=2,
        config=config,
        corpus_counts=corpus_counts,
        artifact_kind="retrieval",
    )
    progress = EvalRunProgress(run_id="interval-test", artifact_kind="retrieval")
    checkpoint_file = checkpoint_path(output)

    after_record(progress, "r1", artifact=_sample_retrieval_artifact("r1"), checkpoint_ctx=checkpoint_ctx)
    assert not checkpoint_file.exists()

    after_record(progress, "r2", artifact=_sample_retrieval_artifact("r2"), checkpoint_ctx=checkpoint_ctx)
    assert checkpoint_file.exists()

    payload = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    assert payload["records_processed"] == 2
    assert payload["version"] == CHECKPOINT_VERSION


def test_maybe_checkpoint_disabled_when_interval_zero(tmp_path: Path) -> None:
    output = tmp_path / "run.json"
    config = _sample_config()
    checkpoint_ctx = CheckpointContext(
        output_path=output,
        interval=0,
        config=config,
        corpus_counts=CorpusCounts(published=1),
        artifact_kind="retrieval",
    )
    progress = EvalRunProgress(run_id="no-checkpoint", artifact_kind="retrieval")
    after_record(
        progress,
        "r1",
        artifact=_sample_retrieval_artifact("r1"),
        checkpoint_ctx=checkpoint_ctx,
    )
    assert not checkpoint_path(output).exists()


def test_resume_skips_completed_ids() -> None:
    progress = EvalRunProgress(run_id="resume-test", artifact_kind="retrieval")
    progress.mark_evaluated("done-1", _sample_retrieval_artifact("done-1"))
    assert progress.should_skip("done-1")
    assert not progress.should_skip("new-1")


def test_config_mismatch_on_resume_raises(tmp_path: Path) -> None:
    config = _sample_config()
    progress = EvalRunProgress(run_id="mismatch", artifact_kind="retrieval")
    checkpoint_file = tmp_path / "run-checkpoint.json"
    write_checkpoint(
        progress,
        checkpoint_file,
        config=config,
        corpus_counts=CorpusCounts(published=1),
    )

    wrong_config = _sample_config(k=10)
    with pytest.raises(ValueError, match="config mismatch"):
        load_checkpoint(checkpoint_file, wrong_config)


def test_ensure_resume_policy_errors_without_resume_flag(tmp_path: Path) -> None:
    output = tmp_path / "run.json"
    checkpoint_file = checkpoint_path(output)
    checkpoint_file.write_text("{}", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        ensure_resume_policy(output, resume=False)
    assert exc_info.value.code == 1


def test_init_progress_loads_checkpoint_when_resume(tmp_path: Path) -> None:
    output = tmp_path / "run.json"
    config = _sample_config()
    progress = EvalRunProgress(run_id="loaded-run", artifact_kind="retrieval")
    progress.mark_evaluated("saved", _sample_retrieval_artifact("saved"))
    write_checkpoint(
        progress,
        checkpoint_path(output),
        config=config,
        corpus_counts=CorpusCounts(published=5),
    )

    loaded = init_progress(
        output_path=output,
        resume=True,
        config=config,
        run_id="ignored",
        artifact_kind="retrieval",
    )
    assert loaded.run_id == "loaded-run"
    assert loaded.should_skip("saved")


def test_delete_checkpoint_removes_file(tmp_path: Path) -> None:
    checkpoint_file = tmp_path / "run-checkpoint.json"
    checkpoint_file.write_text("{}", encoding="utf-8")
    delete_checkpoint(checkpoint_file)
    assert not checkpoint_file.exists()
