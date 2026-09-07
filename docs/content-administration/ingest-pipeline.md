# Ingest pipeline

Source documents become modules through Celery workers. Dual-path merge and content versioning: [Modules, cards, and families](../concepts/modules-cards-families.md). Admin upload sequence: [Upload and ingest sources](ingest-sources.md).

## Stage names

Workers persist these stage names on `ingestion_run_step`:

| Stage name | What it does |
|---|---|
| `thumbnail` | Optional thumbnail generation |
| `extract` | Page extract, calibration, outline assembly |
| `module_identify` | LLM identifies module candidates from the corpus |
| `candidate_merge` | Batch-wide merge of same-topic candidates |
| `card_draft` | LLM drafts cards into module rows |
| `quiz_generation` | Post-publish quiz questions |
| `embedding_generation` | Post-publish embeddings |
| `search_metadata_generation` | Module search metadata |
| `card_search_metadata_generation` | Card search metadata |
| `gap_classification` | Behavioural gap tags |
| `trigger_binding` | Trigger bindings |

`extract` includes outline assembly. There is no separate outline stage.

## Extract

For each source document:

1. Count pages.
2. Calibrate text-only versus vision extraction.
3. Extract every page. Persist `source_page` rows with markdown.
4. Assemble the outline from heading lines. Persist `source_document.outline_jsonb`.
5. Fail hard when usable body text is below `extraction_quality_text_empty_min_chars`.
6. Empty outline alone is not fatal.

Optional figure extraction writes `source_image` rows when `INGEST_SOURCE_IMAGE_EXTRACTION_ENABLED` is true. Optional video visual extraction samples frames when `INGEST_VIDEO_VISUAL_EXTRACTION_ENABLED` is true. Those paths are best-effort.

## Module identify

One LLM call (chunked when needed) identifies module candidates from the corpus plus outline. Candidates are ephemeral pipeline state in `module_candidate_draft`.

## Candidate merge

After every source in the batch finishes module identify, a batch-wide merge collapses same-topic candidates. Single-source batches take the same identify → merge → draft path.

## Card draft

The drafter writes module rows and `module_card` rows. When a similar active module exists, card draft writes a dual-path review-pending pair. See [Review dual-path merges](review-merges.md).

Sibling candidates continue. Both dual-path modules enqueue full post-publish.

## Post-publish

After draft, workers generate:

- quizzes (skipped when `assessment_mode` is `read_only`)
- embeddings (cloud and local when configured)
- search metadata
- gap classifications
- trigger bindings

## Admin sequence

1. `POST /admin/ingest/upload` stores files and creates `source_document` rows with `status=uploaded`.
2. `POST /admin/ingest` creates an ingest batch and one ingestion run per source, then enqueues Celery.
3. `GET /admin/ingest/batches/{batch_id}` polls the tree.
4. `POST /admin/ingest/batches/{batch_id}/retry` retries failed retryable stages.

## Next step

[Review dual-path merges](review-merges.md)
