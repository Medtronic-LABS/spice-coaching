# Sync content for offline use

The SDK pulls published content, then works offline.

Route details: [Sync](../api-reference/sync.md).

> **Limitation:** Sync list routes do not paginate yet. Note that while `/telemetry/events` (120/min) and `/coaching/*` (30/min) enforce Redis sliding-window rate limits, `/sync/*` routes are currently unthrottled.

**Before you start:** Read [Authentication](../device-integration/authentication.md). Send `Authorization: Bearer` and `client: mob` when SPICE auth is on. Cache `locales` from `GET /sync/config`. See [Locales](../concepts/locales.md).

## Pull a delta

Use the same `since` ISO-8601 cursor on related routes. On first pull, use a far-past timestamp.

1. Call `GET /sync/config`.
2. Call `GET /sync/modules?since=...`.
3. Call `GET /sync/card-embeddings?since=...` for EDGE mode.
4. Call `GET /sync/source-documents?since=...`.
5. Call `GET /sync/video-progress?since=...`.
6. Call `GET /sync/triggers?since=...` and `GET /sync/gaps?since=...`.
7. Call `GET /sync/chat-faqs?since=...`.
8. Call `GET /sync/badges`.

**Result:** The device stores modules, quizzes, embeddings, documents, triggers, gaps, FAQ chips, and badges. Each bundle includes `server_time_utc`.

## What `/sync/modules` returns

- Published modules and quizzes updated after `since`.
- Thumbnail presigned GET URLs when a thumbnail object path exists.
- `assigned_module_ids` for the authenticated CHW. The list is empty when the user has no assignments. See [Assign modules and documents](../content-administration/assign-content.md).
- `requested_modules` for the CHW training-request history.

Resolve titles with `content[locales.primary]`.

## What `/sync/source-documents` returns

- Presigned GET URLs for documents linked to currently published modules with `updated_at > since`. Retired rows are excluded.
- `assigned_documents` as a full snapshot of the user's document assignments. This list ignores `since`.

Documents can appear in both lists. Union by `source_document_id`.

## Refresh presigned URLs

Call `POST /sync/presigned-urls` with up to 50 object-storage object names. Unresolvable keys are listed in `missing_paths`.

## Next step

[Ask the coaching chatbot](coaching-chat.md)

## See also

* [EDGE mode](../GLOSSARY.md#edge-mode) — uses synced card embeddings for on-device chat
* [Assign modules and documents](../content-administration/assign-content.md) — how `assigned_module_ids` are granted
