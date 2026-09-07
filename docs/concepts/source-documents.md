# Source documents

A [source document](../GLOSSARY.md#source-document) is an uploaded PDF, PPTX, DOCX, audio file, or video file.

## How it works

1. `POST /admin/ingest/upload` stores files and creates rows with `status=uploaded`. Those rows do not sync as knowledge files.
2. `POST /admin/ingest` queues the [ingest](../GLOSSARY.md#ingest) pipeline for staged ids.
3. `POST /admin/knowledge/upload` stores a PDF with `sync_published_visible=true`. That row can sync to devices without ingest.

Audio and video files store `duration_ms`. Media upload size is subject to server body limits (default 100 MB).

Upload and knowledge routes: [Admin ingest](../api-reference/admin-ingest.md) and [Upload and ingest sources](../content-administration/ingest-sources.md).

## Status

| Status | Meaning |
|---|---|
| `uploaded` | Staged. Ready for ingest or knowledge assignment. |
| `ingested` | Pipeline finished. |
| `failed` | A pipeline stage failed. You can re-queue. |
| `retired` | Soft-deleted. Sync excludes these rows. |

Duplicate detection uses SHA256 against `uploaded` or `ingested` rows in the selected tenant.

## Two uses

- **Ingest source** — becomes modules and cards.
- **Knowledge library** — syncs as a document the CHW can open. See [Knowledge library](../content-administration/knowledge-library.md).

A document can appear in both the module-linked list and the assigned-document list on sync. Clients union by `source_document_id`.

## Next step

[Modules, cards, and families](modules-cards-families.md)
