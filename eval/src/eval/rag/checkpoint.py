"""Checkpoint save/load for resumable eval batch runs."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Literal

from eval.rag.report import RecordArtifact

CHECKPOINT_VERSION = 1
ArtifactKind = Literal["retrieval", "dict"]


class SkipKind(str, Enum):
    UNANSWERABLE = "unanswerable"
    UNRESOLVABLE = "unresolvable"


@dataclass(frozen=True)
class EvalRunConfig:
    method: str
    dataset_path: str
    k: int
    language: str
    tenant_id: int | None
    generate: bool = False
    local_card: bool = False
    llm_judge: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "dataset_path": self.dataset_path,
            "k": self.k,
            "language": self.language,
            "tenant_id": self.tenant_id,
            "generate": self.generate,
            "local_card": self.local_card,
            "llm_judge": self.llm_judge,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> EvalRunConfig:
        return cls(
            method=str(raw.get("method", "")),
            dataset_path=str(raw.get("dataset_path", "")),
            k=int(raw.get("k", 0)),
            language=str(raw.get("language", "bn")),
            tenant_id=raw.get("tenant_id") if raw.get("tenant_id") is None else int(raw["tenant_id"]),
            generate=bool(raw.get("generate", False)),
            local_card=bool(raw.get("local_card", False)),
            llm_judge=bool(raw.get("llm_judge", False)),
        )


@dataclass(frozen=True)
class CorpusCounts:
    published: int
    embedded: int | None = None


@dataclass(frozen=True)
class CheckpointContext:
    output_path: Path
    interval: int
    config: EvalRunConfig
    corpus_counts: CorpusCounts
    artifact_kind: ArtifactKind


@dataclass
class EvalRunProgress:
    run_id: str
    artifact_kind: ArtifactKind
    completed_record_ids: set[str] = field(default_factory=set)
    artifacts: list[RecordArtifact | dict[str, object]] = field(default_factory=list)
    skipped_unanswerable_count: int = 0
    skipped_unresolvable_count: int = 0
    records_processed: int = 0

    def should_skip(self, record_id: str) -> bool:
        return record_id in self.completed_record_ids

    def mark_evaluated(
        self,
        record_id: str,
        artifact: RecordArtifact | dict[str, object],
    ) -> None:
        if record_id in self.completed_record_ids:
            return
        self.completed_record_ids.add(record_id)
        self.artifacts.append(artifact)
        self.records_processed += 1

    def mark_skipped(self, record_id: str, skip_kind: SkipKind) -> None:
        if record_id in self.completed_record_ids:
            return
        self.completed_record_ids.add(record_id)
        if skip_kind == SkipKind.UNANSWERABLE:
            self.skipped_unanswerable_count += 1
        else:
            self.skipped_unresolvable_count += 1
        self.records_processed += 1

    def retrieval_artifacts(self) -> list[RecordArtifact]:
        return [artifact for artifact in self.artifacts if isinstance(artifact, RecordArtifact)]

    def dict_artifacts(self) -> list[dict[str, object]]:
        return [artifact for artifact in self.artifacts if isinstance(artifact, dict)]


def checkpoint_path(output: Path) -> Path:
    return output.with_name(f"{output.stem}-checkpoint.json")


def _config_mismatch_fields(expected: EvalRunConfig, actual: EvalRunConfig) -> list[str]:
    mismatches: list[str] = []
    for key, expected_value in expected.as_dict().items():
        actual_value = actual.as_dict()[key]
        if actual_value != expected_value:
            mismatches.append(f"{key}: expected {expected_value!r}, got {actual_value!r}")
    return mismatches


def _artifact_to_dict(
    artifact: RecordArtifact | dict[str, object],
    artifact_kind: ArtifactKind,
) -> dict[str, object]:
    if artifact_kind == "retrieval":
        if not isinstance(artifact, RecordArtifact):
            raise TypeError("retrieval checkpoint requires RecordArtifact")
        return asdict(artifact)
    if not isinstance(artifact, dict):
        raise TypeError("dict checkpoint requires dict artifact")
    return artifact


def _artifact_from_dict(
    raw: dict[str, object],
    artifact_kind: ArtifactKind,
) -> RecordArtifact | dict[str, object]:
    if artifact_kind == "retrieval":
        return RecordArtifact(**raw)
    return dict(raw)


def write_checkpoint(
    progress: EvalRunProgress,
    checkpoint_file: Path,
    *,
    config: EvalRunConfig,
    corpus_counts: CorpusCounts,
) -> None:
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "version": CHECKPOINT_VERSION,
        "run_status": "in_progress",
        "run_id": progress.run_id,
        "artifact_kind": progress.artifact_kind,
        "config": config.as_dict(),
        "corpus_published_count": corpus_counts.published,
        "corpus_embedded_count": corpus_counts.embedded,
        "skipped_unanswerable_count": progress.skipped_unanswerable_count,
        "skipped_unresolvable_count": progress.skipped_unresolvable_count,
        "completed_record_ids": sorted(progress.completed_record_ids),
        "artifacts": [_artifact_to_dict(artifact, progress.artifact_kind) for artifact in progress.artifacts],
        "checkpoint_at": datetime.now(UTC).isoformat(),
        "records_processed": progress.records_processed,
    }
    temp_path = checkpoint_file.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temp_path, checkpoint_file)


def load_checkpoint(
    checkpoint_file: Path,
    expected_config: EvalRunConfig,
) -> EvalRunProgress:
    raw = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{checkpoint_file}: checkpoint root must be a JSON object")

    version = raw.get("version")
    if version != CHECKPOINT_VERSION:
        raise ValueError(
            f"{checkpoint_file}: unsupported checkpoint version {version!r} (expected {CHECKPOINT_VERSION})"
        )

    config_raw = raw.get("config")
    if not isinstance(config_raw, dict):
        raise ValueError(f"{checkpoint_file}: checkpoint missing config object")
    loaded_config = EvalRunConfig.from_dict(config_raw)
    mismatches = _config_mismatch_fields(expected_config, loaded_config)
    if mismatches:
        raise ValueError(f"{checkpoint_file}: checkpoint config mismatch: " + "; ".join(mismatches))

    artifact_kind_raw = raw.get("artifact_kind")
    if artifact_kind_raw not in {"retrieval", "dict"}:
        raise ValueError(f"{checkpoint_file}: invalid artifact_kind {artifact_kind_raw!r}")
    artifact_kind = artifact_kind_raw

    completed_ids_raw = raw.get("completed_record_ids")
    if not isinstance(completed_ids_raw, list):
        raise ValueError(f"{checkpoint_file}: checkpoint missing completed_record_ids array")
    completed_record_ids = {str(item) for item in completed_ids_raw}

    artifacts_raw = raw.get("artifacts")
    if not isinstance(artifacts_raw, list):
        raise ValueError(f"{checkpoint_file}: checkpoint missing artifacts array")
    artifacts: list[RecordArtifact | dict[str, object]] = []
    for item in artifacts_raw:
        if not isinstance(item, dict):
            continue
        artifacts.append(_artifact_from_dict(item, artifact_kind))

    run_id = str(raw.get("run_id", ""))
    if not run_id:
        raise ValueError(f"{checkpoint_file}: checkpoint missing run_id")

    return EvalRunProgress(
        run_id=run_id,
        artifact_kind=artifact_kind,
        completed_record_ids=completed_record_ids,
        artifacts=artifacts,
        skipped_unanswerable_count=int(raw.get("skipped_unanswerable_count", 0)),
        skipped_unresolvable_count=int(raw.get("skipped_unresolvable_count", 0)),
        records_processed=int(raw.get("records_processed", 0)),
    )


def delete_checkpoint(checkpoint_file: Path) -> None:
    if checkpoint_file.exists():
        checkpoint_file.unlink()


def ensure_resume_policy(output_path: Path, resume: bool) -> None:
    checkpoint_file = checkpoint_path(output_path)
    if checkpoint_file.exists() and not resume:
        print(
            f"error: checkpoint exists at {checkpoint_file}; "
            "pass --resume to continue or delete the checkpoint file",
            file=sys.stderr,
        )
        raise SystemExit(1)


def init_progress(
    *,
    output_path: Path,
    resume: bool,
    config: EvalRunConfig,
    run_id: str,
    artifact_kind: ArtifactKind,
) -> EvalRunProgress:
    checkpoint_file = checkpoint_path(output_path)
    if resume and checkpoint_file.exists():
        return load_checkpoint(checkpoint_file, config)
    return EvalRunProgress(run_id=run_id, artifact_kind=artifact_kind)


def after_record(
    progress: EvalRunProgress,
    record_id: str,
    *,
    artifact: RecordArtifact | dict[str, object] | None = None,
    skip_kind: SkipKind | None = None,
    checkpoint_ctx: CheckpointContext | None = None,
) -> None:
    if progress.should_skip(record_id):
        return
    if skip_kind is not None:
        progress.mark_skipped(record_id, skip_kind)
    elif artifact is not None:
        progress.mark_evaluated(record_id, artifact)
    else:
        raise ValueError("after_record requires artifact or skip_kind")

    if checkpoint_ctx is not None:
        maybe_checkpoint(progress, checkpoint_ctx)


def maybe_checkpoint(progress: EvalRunProgress, checkpoint_ctx: CheckpointContext) -> None:
    if checkpoint_ctx.interval <= 0:
        return
    if progress.records_processed % checkpoint_ctx.interval != 0:
        return
    write_checkpoint(
        progress,
        checkpoint_path(checkpoint_ctx.output_path),
        config=checkpoint_ctx.config,
        corpus_counts=checkpoint_ctx.corpus_counts,
    )
