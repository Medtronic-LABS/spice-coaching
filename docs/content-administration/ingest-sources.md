# Upload and ingest sources

[Ingest](../GLOSSARY.md#ingest) turns PDF, PPTX, DOCX, audio, and video [source documents](../concepts/source-documents.md) into module drafts.

**Before you start:** Use an [Area Manager](../GLOSSARY.md#area-manager) or [Super Admin](../GLOSSARY.md#super-admin) session. Confirm `platform-celery-worker` is running. Maximum 10 files per upload. Maximum 10 source ids per [ingest batch](../GLOSSARY.md#ingest-batch).

Route details: [Admin ingest](../api-reference/admin-ingest.md).

## Upload files

1. Call `POST /admin/ingest/upload` with multipart field `files`.
2. Optional form fields: `titles`, `descriptions`, `override_duplicates`, `content_domains` (`clinical` | `digital` | `operational`).
3. Read `sources[].source_document_id` from the `201` response.

**Result:** Rows exist with `status=uploaded`. The pipeline is not queued. `sync_published_visible` is always false on this route.

Unresolved duplicates return `409` `duplicate_content`. Nothing is written.

## Queue the pipeline

1. Call `POST /admin/ingest` with `source_document_ids`.
2. Optional body fields: `override_duplicates`, `ingestion_instructions`, `cards_per_module`, `quizzes_per_module`, `assessment_mode`.
3. Poll `GET /admin/ingest/batches/{batch_id}`.

**Result:** The response is `202` with `batch_id` and `poll_url`. Batch status rolls up to `queued`, `running`, `succeeded`, `failed`, or `partially_succeeded`.

`read_only` assessment mode skips post-publish quiz generation. The `card_draft` stage always attempts published-module merge.

Accepts `uploaded` status. Also `failed` (re-queue) and `ingested` only when `override_duplicates` is true for that id.

Audio and video files are probed with ffprobe. `duration_ms` is stored in milliseconds. Media upload size is governed by web server / proxy limits (default 100 MB).

When at least one stage is retryable, the poll payload includes `retry_url`. Call `POST /admin/ingest/batches/{batch_id}/retry`.

Stage names and extract behaviour: [Ingest pipeline](ingest-pipeline.md).

## Next step

[Review dual-path merges](review-merges.md)
