# Sync

Delta synchronization routes for mobile clients. Enables the Android SDK to pull content updates incrementally, cache them locally, and operate completely offline.

**How to use:** [Sync content for offline use](../device-coaching/sync-content.md).

**Auth required:** Yes when SPICE auth is on. Hierarchy role `SHASTIYA_KORMI` or `PO`. Super Admin has no `/sync/*` grant.

**Pagination & Cursoring:** Sync list routes do not paginate. Instead, pass the same `since` ISO-8601 UTC timestamp (e.g. `2026-01-01T00:00:00Z`) across all delta endpoints. On initial pull, use an ancient timestamp (`1970-01-01T00:00:00Z`).

## GET /sync/config

Fetches runtime thresholds, primary/supported locales, and server clock.

**Response `200` (`ConfigSyncBundle`)**

| Field | Type | Description |
|---|---|---|
| `thresholds` | object | Key-value dictionary of server thresholds (e.g. quiz pass percentage, idle timeouts). |
| `locales.primary` | string | CHW-facing primary locale code (`bn`). |
| `locales.supported` | string[] | List of supported locale codes. |
| `server_time_utc` | string | Current server UTC time (ISO-8601). Store this as the `since` cursor for the next sync. |

## GET /sync/modules

Pulls published modules and quizzes modified after `since`.

**Query Parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `since` | ISO-8601 | Yes | Inclusive timestamp cursor matching `updated_at`. |

**Response `200` (`ModulesSyncBundle`)**

| Field | Type | Description |
|---|---|---|
| `modules` | array | Array of `ModuleSyncPayload` objects: published module details, cards, quizzes, and thumbnail presigned URLs. |
| `module_families` | array | Array of `ModuleFamilySyncPayload` objects: stable family ID and latest published module ID. |
| `assigned_module_ids` | array | Array of `{ module_id, assigned_at }` records for the authenticated CHW. |
| `requested_modules` | array | Array of self-requested training module records from the CHW's telemetry history. |
| `server_time_utc` | string | Server time for cursor progression. |

## GET /sync/card-embeddings

Pulls local card embeddings for on-device EDGE mode chat.

**Query Parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `since` | ISO-8601 | Yes | Inclusive timestamp cursor. |

**Response `200` (`CardEmbeddingsSyncBundle`)**

| Field | Type | Description |
|---|---|---|
| `cards` | array | Array of `CardEmbeddingPayload` objects: `card_id` (UUID), `module_id` (UUID), `card_family_id` (UUID), and `embedding` (768-dimension float array). |
| `server_time_utc` | string | Server time for cursor progression. |

Cards without a persisted local embedding are omitted from this bundle.

## GET /sync/source-documents

Pulls documents linked to published modules and assigned knowledge library documents.

**Query Parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `since` | ISO-8601 | Yes | Filter for module-linked documents (`updated_at > since`). |

**Response `200` (`SourceDocumentsSyncBundle`)**

| Field | Type | Description |
|---|---|---|
| `documents` | array | Documents linked to currently published modules updated after `since`. |
| `assigned_documents` | array | Full snapshot of source documents directly assigned to the CHW (ignores `since`). |
| `server_time_utc` | string | Server time for cursor progression. |

Each document record includes `source_document_id`, `title`, `storage_path`, `thumbnail_storage_path`, `duration_ms` (for media), and presigned GET URLs. Clients union both arrays by `source_document_id`.

## GET /sync/video-progress

Retrieves incremental video watch progress for assigned media.

**Query Parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `since` | ISO-8601 | Yes | Inclusive timestamp cursor. |

**Response `200` (`VideoProgressSyncBundle`)**

| Field | Type | Description |
|---|---|---|
| `progress` | array | Array of `VideoProgressPayload` items: `source_document_id`, `last_position_ms`, `percent_watched`, `updated_at`. |
| `server_time_utc` | string | Server time for cursor progression. |

## GET /sync/triggers

Retrieves assessment-due trigger definitions and module bindings.

**Query Parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `since` | ISO-8601 | Yes | Inclusive timestamp cursor. |

**Response `200` (`TriggersSyncBundle`)**

| Field | Type | Description |
|---|---|---|
| `triggers` | array | Array of `TriggerDefinitionSyncPayload` objects: `trigger_code`, `predicate_jsonb`, `status`. |
| `bindings` | array | Array of `ModuleTriggerBindingSyncPayload` objects: `trigger_definition_id`, `module_id`, `priority_weight`. |
| `server_time_utc` | string | Server time for cursor progression. |

## GET /sync/gaps

Pulls behavioural gap rules, CHW tracking state, and accumulated learning points.

**Query Parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `since` | ISO-8601 | Yes | Inclusive timestamp cursor. |

**Response `200` (`GapsSyncBundle`)**

| Field | Type | Description |
|---|---|---|
| `gaps` | array | Canonical gap definitions and `detection_rule_jsonb` operator trees. |
| `gap_states` | array | Per-CHW state records (`severity_current`, `occurrence_count`, `failed_attempts_count`). |
| `quiz_states` | array | Question attempt history and failed question tracking. |
| `completed_module_ids` | UUID[] | Full list of published modules completed by this CHW. |
| `total_points` | int | Total learning points earned by the CHW. |
| `server_time_utc` | string | Server time for cursor progression. |

## GET /sync/chat-faqs

Retrieves ranked suggestion chips synthesized from telemetry for the coaching chat interface.

**Query Parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `since` | ISO-8601 | Yes | Inclusive timestamp cursor. |

**Response `200` (`ChatFaqsSyncBundle`)**

| Field | Type | Description |
|---|---|---|
| `faqs` | array | Ranked FAQ items with locale-keyed `question` map, `occurrence_count`, and `rank`. |
| `server_time_utc` | string | Server time for cursor progression. |

## GET /sync/badges

Retrieves badge definitions and awards. This is a full snapshot route (does not use `since`).

**Response `200` (`BadgesSyncBundle`)**

| Field | Type | Description |
|---|---|---|
| `available_badges` | array | All active badges with `title`, `description`, `icon_url`, and linked `module_ids`. |
| `earned_badges` | array | Badges earned by the authenticated CHW with `earned_at` timestamps. |
| `server_time_utc` | string | Server time. |

## POST /sync/presigned-urls

Batch refreshes presigned download URLs for cached object storage paths when earlier URLs expire.

**Request**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `storage_paths` | string[] | Yes | 1 to 50 object storage paths. |

**Response `200`**

| Field | Type | Description |
|---|---|---|
| `urls` | array | Array of `{ storage_path, presigned_url, expires_at }` objects. |
| `missing_paths` | string[] | Any object paths that could not be found or presigned. |
| `server_time_utc` | string | Server time. |

**Errors**

| Status | Meaning |
|---|---|
| `401` | Missing or invalid token (`not_authenticated`) |
| `403` | Missing grant (e.g. Super Admin or unmapped user) |
| `422` | Validation failure (e.g. missing `since` cursor or invalid format) |

## Next step

[Telemetry](telemetry.md)
