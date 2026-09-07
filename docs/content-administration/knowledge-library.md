# Knowledge library

Knowledge documents sync to devices without a full module ingest. These rows have `sync_published_visible=true`.

**Before you start:** Upload PDFs only on this path. Do not use this route for ingest sources that must become modules.

## Upload a knowledge PDF

1. Call `POST /admin/knowledge/upload`.
2. Use whole-file mode, or send `splits` to cut page ranges into separate documents.
3. Assign the document when CHWs must receive it. See [Assign modules and documents](assign-content.md).

**Result:** Rows exist with `status=uploaded` and `sync_published_visible=true`. The ingest pipeline is not queued.

Duplicate content without override returns `409` `duplicate_content`.

## List uploaders

Call `GET /admin/knowledge/uploaders` to list hierarchy users who uploaded at least one active knowledge document in the selected tenant.

## Retire a knowledge document

Call `DELETE /admin/knowledge/{source_document_id}`.

**Result:** Status becomes `retired`. Ingest docs (`sync_published_visible=false`) return `403`. Success is `204`.

## Next step

[Manage the org hierarchy](manage-hierarchy.md)
