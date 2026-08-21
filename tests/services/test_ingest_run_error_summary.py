"""Unit tests for ingest partial-success error summarization."""

from __future__ import annotations

from types import SimpleNamespace

from mc_contracts.errors import ErrorCode
from platform_service.services.ingest_run_error_summary import (
    summarize_batch_error,
    summarize_error_from_failed_children,
    summarize_ingestion_run_error,
)
from platform_service.services.run_state_service import (
    BATCH_PARTIALLY_SUCCEEDED,
    BATCH_SUCCEEDED,
    RUN_FAILED,
    RUN_PARTIALLY_SUCCEEDED,
    STAGE_CARD_DRAFT,
    STAGE_EXTRACT,
    STAGE_GAP_CLASSIFICATION,
    STAGE_MODULE_IDENTIFY,
    STAGE_QUIZ_GENERATION,
    STEP_FAILED,
    STEP_SUCCEEDED,
)


def _step(
    *,
    stage: str,
    status: str = STEP_FAILED,
    error_code: str | None = None,
    error_message: str | None = None,
    error: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        stage=stage,
        status=status,
        error_code=error_code,
        error_message=error_message,
        error_jsonb=error,
    )


class TestSummarizeIngestionRunError:
    def test_none_and_empty(self) -> None:
        assert summarize_ingestion_run_error(None) is None
        assert summarize_ingestion_run_error([]) is None  # type: ignore[arg-type]
        assert summarize_ingestion_run_error({}) is None

    def test_strips_pipeline_claim(self) -> None:
        out = summarize_ingestion_run_error(
            {
                "_pipeline_claim": {"claim_token": "x"},
                "failed_stage": STAGE_MODULE_IDENTIFY,
                "code": ErrorCode.IDENTIFY_NO_CANDIDATES.value,
            },
            status=RUN_PARTIALLY_SUCCEEDED,
        )
        assert out is not None
        assert "_pipeline_claim" not in out
        assert out["message"] == ("Module identify stage completed without emitting any candidates.")

    def test_maps_technical_message_to_user_copy(self) -> None:
        out = summarize_ingestion_run_error(
            {
                "failed_stage": STAGE_MODULE_IDENTIFY,
                "message": "zero candidates were identified",
                "code": ErrorCode.IDENTIFY_NO_CANDIDATES.value,
            }
        )
        assert out is not None
        assert out["message"] == (
            "We couldn't find any training modules in this document. "
            "Try a document with clearer sections or headings."
        )

    def test_maps_ffmpeg_technical_step_message(self) -> None:
        steps = [
            _step(
                stage=STAGE_EXTRACT,
                error_code=ErrorCode.EXTRACT_FAILED.value,
                error_message="ffmpeg chunk encode failed (start_ms=0): bad data",
                error={"reason": "media_encode_failed", "detail": "ffmpeg chunk encode failed"},
            ),
        ]
        out = summarize_ingestion_run_error(
            {"failed_stage": STAGE_EXTRACT, "code": ErrorCode.EXTRACT_FAILED.value},
            steps=steps,  # type: ignore[arg-type]
            status=RUN_FAILED,
        )
        assert out is not None
        assert "couldn't process the audio" in out["message"]
        assert "ffmpeg" not in out["message"]
        assert out["causes"][0]["detail"] == "ffmpeg chunk encode failed"

    def test_draft_failures_message(self) -> None:
        out = summarize_ingestion_run_error(
            {
                "failed_stage": STAGE_CARD_DRAFT,
                "failed_stages": [STAGE_CARD_DRAFT],
                "draft_failures": 1,
                "drafts_produced": 2,
            },
            status=RUN_PARTIALLY_SUCCEEDED,
        )
        assert out is not None
        assert out["message"] == (
            "Card drafting failed for 1 of 3 module candidate(s); 2 module(s) were still produced."
        )

    def test_post_publish_failed_stages_message(self) -> None:
        out = summarize_ingestion_run_error(
            {
                "failed_stages": [STAGE_QUIZ_GENERATION, STAGE_GAP_CLASSIFICATION],
            },
            status=RUN_PARTIALLY_SUCCEEDED,
        )
        assert out is not None
        assert out["message"] == (
            "Post-publish step(s) failed: Generating quiz, Classifying behavioural gaps."
        )

    def test_single_failed_stage_message(self) -> None:
        out = summarize_ingestion_run_error({"failed_stage": STAGE_MODULE_IDENTIFY})
        assert out is not None
        assert out["message"] == "Identifying modules failed."

    def test_causes_from_steps(self) -> None:
        steps = [
            _step(
                stage=STAGE_CARD_DRAFT,
                error_code=ErrorCode.DRAFT_FAILED.value,
                error_message="bad cand",
            ),
            _step(stage=STAGE_MODULE_IDENTIFY, status=STEP_SUCCEEDED),
        ]
        out = summarize_ingestion_run_error(
            {"failed_stages": [STAGE_CARD_DRAFT], "draft_failures": 1, "drafts_produced": 0},
            steps=steps,  # type: ignore[arg-type]
            status=RUN_PARTIALLY_SUCCEEDED,
        )
        assert out is not None
        assert out["causes"] == [
            {
                "stage": STAGE_CARD_DRAFT,
                "code": ErrorCode.DRAFT_FAILED.value,
                "message": (
                    "We couldn't draft module cards for one or more candidates. "
                    "Try retrying or reviewing the source document."
                ),
            }
        ]
        assert "couldn't draft module cards" in out["message"]


class TestSummarizeErrorFromFailedChildren:
    def test_uses_first_failed_child_message(self) -> None:
        nodes = [
            {
                "key": "chunk",
                "status": STEP_FAILED,
                "error_code": ErrorCode.IDENTIFY_FAILED.value,
                "error_message": "ai-runtime timeout",
                "error": {"type": "Timeout", "message": "ai-runtime timeout"},
                "children": [],
            }
        ]
        out = summarize_error_from_failed_children(nodes)
        assert out is not None
        assert out["message"] == (
            "Our AI service was temporarily unavailable. Please retry in a few minutes."
        )
        assert out["causes"][0]["stage"] == "chunk"


class TestSummarizeBatchError:
    def test_none_when_not_partial(self) -> None:
        assert summarize_batch_error(BATCH_SUCCEEDED, [{"message": "x"}]) is None

    def test_aggregates_partial_sources(self) -> None:
        out = summarize_batch_error(
            BATCH_PARTIALLY_SUCCEEDED,
            [
                {
                    "code": ErrorCode.IDENTIFY_NO_CANDIDATES.value,
                    "message": "Module identify stage completed without emitting any candidates.",
                },
                None,
            ],
            document_labels=["doc-a.pdf", "doc-b.pdf"],
        )
        assert out is not None
        assert out["message"] == "1 of 2 sources partially succeeded."
        assert out["causes"] == [
            {
                "document_index": 0,
                "document_label": "doc-a.pdf",
                "message": "Module identify stage completed without emitting any candidates.",
                "code": ErrorCode.IDENTIFY_NO_CANDIDATES.value,
            }
        ]
