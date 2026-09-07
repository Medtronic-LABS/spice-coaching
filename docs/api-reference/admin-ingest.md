# Admin ingest

Upload sources, queue the pipeline, poll progress, and resolve dual-path merges.

**How to use:** [Upload and ingest sources](../content-administration/ingest-sources.md) and [Review dual-path merges](../content-administration/review-merges.md).

**Auth required:** Yes when SPICE auth is on. Hierarchy role `AREA_MANAGER` or `SUPER_ADMIN`.

## POST /admin/ingest/upload

Uploads one or more source files. Multipart field `files`, max 10. Creates `source_document` rows with `status=uploaded`. Does not queue the pipeline. `sync_published_visible` is always false.

Optional form fields: `titles`, `descriptions`, `override_duplicates`, `content_domains` (`clinical` | `digital` | `operational`).

Audio and video files are probed with ffprobe. `duration_ms` is stored in milliseconds. Media upload size is governed by web server / proxy limits (default 100 MB). Duplicate detection uses SHA256 against `uploaded` or `ingested` rows in the selected tenant.

**Response `201`**

| Field | Type | Description |
|---|---|---|
| `status` | string | `uploaded` |
| `sources` | array | Each row has `source_document_id`, `title`, `source_type`, `stored_path`, `content_domain`, `status` |

**Errors**

| Status | Meaning |
|---|---|
| `409` | `duplicate_content`. Nothing is written. |
| `413` | Payload too large |
| `422` | Validation failure |

## POST /admin/ingest

Queues extract → identify → merge → draft on `platform-celery-worker`.

**Request**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `source_document_ids` | UUID[] | Yes | 1 to 10 ids |
| `assessment_mode` | enum | No | `read_only` skips quiz generation |
| `ingestion_instructions` | string | No | Reviewer hint for the drafter |
| `cards_per_module` | int | No | Cardinality target |
| `quizzes_per_module` | int | No | Cardinality target |
| `override_duplicates` | bool[] | No | Aligned to ids. Re-ingest `ingested` rows when true |

**Response `202`**

| Field | Type | Description |
|---|---|---|
| `status` | string | `batch_queued` |
| `batch_id` | UUID | Poll key |
| `poll_url` | string | Path to poll |
| `sources` | array | Queued sources with `run_id` |

## GET /admin/ingest/batches/{batch_id}

Tree-shaped progress. Batch status: `queued` | `running` | `succeeded` | `failed` | `partially_succeeded`. Includes `retry_url` when at least one stage is retryable.

## POST /admin/ingest/batches/{batch_id}/retry

Retries every retryable failed stage in the batch.

## POST /admin/ingest/modules/{module_id}/override-merge

Promotes the secondary dual-path module for a primary `module_id`. Retires the primary and the matched source module. Sets the secondary to `draft`.

## POST /admin/ingest/modules/{module_id}/split-merge

Keeps the dual-path primary as `draft`. Retires the secondary. Does not mutate the matched source module.

## GET /admin/ingestion-runs

List pipeline runs. Filters include `status`, `q`, `ingested_by`, `limit`, `offset`, `sort_by`, `sort_dir`. Dual-path `review_pending` secondaries are excluded from the module count.

## GET /admin/source-documents

Admin catalog. Filters include `status`, `sync_published_visible`, `source_type`, `q`, `uploaded_by`, `assigned`, and geography ids.

`PATCH /admin/source-documents/{source_document_id}` updates `title` and/or `description` without re-ingest.

## PUT /admin/source-documents/{source_document_id}/thumbnail

Replaces the source document thumbnail.

## POST /admin/knowledge/upload

Uploads one PDF with `sync_published_visible=true`. Does not enqueue ingest. Whole-file mode omits `splits`. Split mode cuts page ranges into separate documents. Duplicate content without override returns `409` `duplicate_content`.

`GET /admin/knowledge/uploaders` lists hierarchy users who uploaded at least one active knowledge document in the selected tenant.

`DELETE /admin/knowledge/{source_document_id}` retires a knowledge document (`204`). Ingest docs return `403`.

## Next step

[Admin modules](admin-modules.md)
