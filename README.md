# MicroCoaching Backend

MicroCoaching is implemented as a stateful platform service plus a private AI runtime inside one monorepo.

This document is the canonical reference for:
- the backend architecture
- the public and internal endpoint contract
- the current implementation status

Old drifted route names are not part of the contract and should not be used.

## Quick Start Docs

- Docs index and reading order: `docs/README.md`
- Setup issues and fixes: `docs/SETUP_TROUBLESHOOTING.md`
- Codebase map and ownership: `docs/PROJECT_NAVIGATION.md`

## Architecture

### Deployables

`platform-api`
- Public API for the Android SDK, admin flows, telemetry ingest, sync, and dashboards
- Owns PostgreSQL writes, ClickHouse writes, orchestration, and final response validation

`platform-worker`
- Async worker process from the same `platform_service` codebase
- Owns ingestion jobs, quiz jobs, and queued gap-profile updates

`ai-runtime`
- Private internal inference service
- Owns model-provider execution, embedding generation, and runtime response parsing
- Does not own PostgreSQL, ClickHouse, or public product workflows

### Shared Packages

`packages/contracts`
- Pydantic contracts, enums, DTOs

`packages/foundation`
- Shared config, logging, tracing, lightweight infra helpers, and the vendor-agnostic `VectorStore` protocol

### Ownership Rules

Platform owns:
- PostgreSQL schema and repositories
- Alembic migrations
- telemetry ingest and analytics writes
- sync contracts
- final coaching-card validation
- admin and dashboard APIs

AI runtime owns:
- provider adapters
- raw generation execution
- embedding generation
- runtime parsing

Shared packages do not own:
- SQLAlchemy models
- repositories
- business workflows
- domain services

## Repo Layout

```text
coaching-platform/
├── pyproject.toml
├── README.md
├── docker-compose.yml
├── infra/
│   ├── alembic/
│   └── alembic.ini
├── packages/
│   ├── contracts/
│   └── foundation/
└── services/
    ├── platform/
    │   └── src/platform_service/
    └── ai-runtime/
        └── src/ai_runtime/
```

## Canonical Endpoint Contract

### API root

Platform API routes are served under **`/medtronics-api`** (configurable via `API_ROOT_PATH`). Paths below are relative to that root; the full URL is `{api_root_path}` + path (e.g. `GET /medtronics-api/ready`, `POST /medtronics-api/coaching/counselling`).

### Authentication

When `SPICE_AUTH_ENABLED=true`, platform-api validates every request (except paths listed in `SPICE_AUTH_EXEMPT_PATHS`, default `ready`) by calling SPICE auth-service `POST {SPICE_AUTH_BASE_URL}/authenticate` with the caller's headers:

- `Authorization: Bearer <jwt>` (required)
- `client` (optional; defaults to `SPICE_AUTH_DEFAULT_CLIENT`, typically `mob` for the Android app)
- `auth-cookie` (optional; web clients)

Set `SPICE_AUTH_BASE_URL` to the auth-service root as seen by platform — either direct (`http://authservice:8089`) or via the nginx reverse proxy (`http://gateway/auth-service`).

Callers must obtain JWTs with the correct SPICE login client: admin web uses `client: web`; the Android SDK uses `client: mob`. Platform forwards the `client` header to `/authenticate`. After authentication, non-`SUPER_USER`/`JOB_USER` principals must bind to a hierarchy `users` row; **authorization** uses that row's DB role against the `api_route` catalog (not SPICE suite-access planes). When the principal is SPICE `isSuperUser`, `isJobUser`, or has token role `SUPER_ADMIN` and no `users` row yet, platform auto-inserts a root `SUPER_ADMIN` row (`parent_id` null, `district_id` null, `tenant_id` from `userDetail.country.tenantId`, name from authenticate first/last/username or `"Admin"`) and continues the request; existing rows are never updated. `SUPER_USER` / `JOB_USER` still bypass route-grant checks. Upstream auth-service failures (timeouts, connection errors, or 5xx) on `/authenticate` and `POST /auth/session` surface to clients as `401` `not_authenticated`.

### Authorization (DB role → route)

When SPICE auth is enabled, endpoint access is granted from Postgres using the authenticated hierarchy user's local role (`users.role_id` → `role.code`) and the `api_route` / `role_route_access` catalog:

| Hierarchy role | Default grants (v1 seed) |
|----------------|--------------------------|
| `AREA_MANAGER` | All `/admin/*` and `/dashboard/*` path templates |
| `PO` | All `/dashboard/*` plus device routes (`/telemetry`, `/sync`, `/morning`, `/coaching`) |
| `SHASTIYA_KORMI` | Device routes only |
| `SUPER_ADMIN` | All catalogued path templates except the `/sync/*` router (grant-based; distinct from SPICE `SUPER_USER` / `JOB_USER` bypass) |

Path templates are exact FastAPI paths relative to `API_ROOT_PATH` (e.g. `/admin/modules/{module_id}`), method-agnostic. Grants are seeded via Alembic and checked on every request. Missing catalog entries and missing grants both return `403` with `insufficient role for this API`. `SUPER_USER` / `JOB_USER` bypass route checks. Handler-level hierarchy scoping for dashboard analytics is unchanged.

Default local/docker behavior keeps `SPICE_AUTH_ENABLED=false` so existing smoke tests work without a running auth-service.

### Error responses (RFC 7807)

Every HTTP error from **platform** and **ai-runtime** returns `Content-Type: application/problem+json` with:

| Field | Meaning |
|-------|---------|
| `type` | Relative catalog pointer `docs/error-codes.json#{code}` |
| `title` | Short title derived from the code |
| `status` | HTTP status |
| `detail` | Technical/debug message (not user-facing copy) |
| `instance` | Request path |
| `code` | Stable machine code — **clients map this to UX strings** |

Client catalogue (descriptions, typical status, domain): [`docs/error-codes.json`](docs/error-codes.json). Server enum: `mc_contracts.errors.ErrorCode`. When adding, removing, or renaming a code, update both in the same PR — pre-commit enforces parity. Validation failures (`422`) include `errors[]` (field locations). Failed ingest steps also persist `error_code` / `error_message` on `ingestion_run_step`, exposed on batch poll nodes.

### Platform API

v3.3 is **module-centric** (not scenario-centric). Device sync uses `/sync/*`; admin content management uses `/admin/modules/*` and `/admin/ingest`. Legacy scenario/counselling route names below are **not implemented** on platform-api — they remain in this doc only as historical context for the ai-runtime `GenerationType` enum.

#### Device-facing

`POST /coaching/rag-query`
- For greeting / chit-chat / crisis-looking messages, a cheap gate may call `ai-runtime` `coaching_chat_route` first: warm locale-language replies (or safety-only crisis guidance) return with empty retrieval fields and skip embed/retrieve
- Otherwise embeds the question, runs vector similarity over published modules via the configured `VectorStore` backend (default: pgvector on `module.embedding`), builds context from module cards, calls `ai-runtime` for a grounded JSON answer, and returns `source_document` rows with optional object-storage presigned URLs for PDF/source attribution
- Grounded `answer` text uses Unicode `• ` bullets (one point per line) when the model returns multiple points, or after server-side fallback formatting of a dense paragraph; chat-route early replies stay short prose
- Request `response_language` selects the answer language: deployment primary locale when empty, or any locale listed in `DEPLOYMENT_ADDITIONAL_LOCALES` (comma-separated; RAG-only — does not expand synced content keys)
- Response includes `suggested_questions`: follow-up questions (in `response_language`) grounded in the retrieved module content (or soft coaching prompts on the chit-chat early-exit path)

`POST /telemetry/events`
- Accepts telemetry batches from the SDK
- Writes analytics rows to ClickHouse
- Queues module-completion and gap-update jobs to Redis for background processing

`GET /sync/modules?since=<ISO-8601>`
- Returns published modules (with quiz payloads) updated after `since`
- Includes module thumbnail presigned GET URLs (`thumbnail_presigned_url` / `thumbnail_presigned_expires_seconds`) when a thumbnail object path exists; null on missing path or soft-failed presign (`has_thumbnail` remains the presence flag)
- Also returns `assigned_module_ids` for the authenticated CHW (direct per-user module assignments); when the user has no assignments, `assigned_module_ids` is empty
- Also returns `requested_modules` — the CHW's full training-request history (`module_id` and/or free-text `requested_module_name`, optional `reason`, `submitted_at`); empty when the CHW has no requests

`GET /sync/triggers?since=<ISO-8601>`
- Returns trigger definitions updated after `since`

`GET /sync/gaps?since=<ISO-8601>`
- Returns behavioural gaps, CHW gap states, module completions, and partial quiz progress for the authenticated CHW (offline device use)

`GET /sync/chat-faqs?since=<ISO-8601>`
- Returns 5–6 ranked FAQ suggestion chips as locale-keyed maps (`question: {"bn": "...", "en": "..."}`) synthesized nightly from clustered `digital_help_used` telemetry for the resolved tenant

`GET /sync/config`
- Returns current config thresholds and deployment `locales` (`primary`, `supported`) for device sync

`GET /sync/source-documents?since=<ISO-8601>`
- Returns presigned GET URLs (and thumbnail URLs) for source documents linked to currently published modules in the tenant with `source_document.updated_at > since` (`source_documents`), excluding `status='retired'`
- Also returns `assigned_documents` — the authenticated user's full current `document_assignment` snapshot with the same download/presign payload shape (ignores `since`; retired excluded). Documents may appear in both lists; clients should union by `source_document_id`
- Each document row includes optional `description` (admin-provided summary, set at upload or via PATCH) and optional `duration_ms` (audio/video length in milliseconds; null for documents and when duration cannot be probed)
- Module card metadata remains on `GET /sync/modules`; this endpoint is the download channel for linked and assigned documents

`GET /sync/badges`
- Returns available tenant badges (`available_badges`) and earned badges (`earned_badges`) for the authenticated CHW (full snapshot; includes image presigned URLs and linked `module_ids`)

`POST /sync/presigned-urls`
- Accepts a batch of object-storage object names (max 50) — the same values returned as `storage_path` / `thumbnail_storage_path` / `image_storage_path` on sync payloads — and returns presigned GET URLs (same normalisation as `GET /admin/files/presigned-url`)
- Partial success: full `bucket/key` refs, legacy filesystem paths, unresolvable keys, or missing objects are listed in `missing_paths`; successful rows are in `urls` with echoed `storage_path`, `presigned_url`, and `expires_seconds`
- Use for on-demand download of object names received from sync payloads without inline presign (e.g. card media `storage_path`)

`GET /sync/video-progress?since=<ISO-8601>`
- Returns delta watch progress (`videos`) for `source_type=video` documents still in the authenticated CHW's `document_assignment` with an existing `chw_video_progress` row where `updated_at > since`
- Progress-only payload (`source_document_id`, `last_position_ms`, `percent_watched`, `completed`, `last_watched_at`); downloads remain on `GET /sync/source-documents`
- Unwatched assigned videos (no progress row) and revoked assignments are omitted; writes stay on `POST /telemetry/events` (`video_progress_updated`)


`GET /morning/cards`
- Returns prioritized module IDs for morning review for the authenticated CHW
- When SPICE auth is disabled, returns an empty card list
- Uses the configured `morning_cards_max` threshold

Module training requests (CHW self-service access) are accepted via `POST /telemetry/events` with `event_type=module_requested` (top-level `module_id` and/or `payload_json.requested_module_name`, optional `payload_json.reason`). See `docs/TELEMETRY_CONTRACT.md`.

#### Admin-facing

`POST /admin/ingest/upload`
- Uploads one or more source files (multipart field `files`, max 10) to object storage and creates `source_document` rows with `status='uploaded'` (pipeline not queued; always `sync_published_visible=false`). Audio and video files are probed with ffprobe at upload time; `duration_ms` is stored in milliseconds, or left null if probing fails. Audio/video upload size is capped by `INGEST_MEDIA_MAX_UPLOAD_BYTES` (default 100 MB); Stage A splits AV sources into transcription chunks during extraction, not at upload.
- Form fields: optional `titles` (JSON array, one title per file in order; if omitted, each title is the file’s basename stem), optional `descriptions` (JSON array of strings or nulls, one per file; omit for null descriptions), optional `override_duplicates` (JSON array of booleans, one per file — when `true`, re-upload even if the file’s `content_sha256` matches an already-`uploaded` or already-`ingested` `source_document` in the selected tenant), optional `content_domains` (JSON array of content domains, one per file — `clinical` | `digital` | `clinical_with_app_workflows`; null/empty entries and omission default to `clinical`)
- Duplicate detection uses SHA256 of file bytes against `source_document` rows in the selected tenant with `status='uploaded'` or `status='ingested'` (`failed` / `ingesting` do not block). Digests are checked before any object-storage or DB writes. Identical digests within the same request return `422` (client must dedupe). Any unresolved duplicate returns `409` Problem Details with `code=duplicate_content` and `conflicts` extensions (atomic — nothing is written).
- Returns `201` with `status: uploaded` and `sources[]` (each with `source_document_id`, `title`, `source_type`, `stored_path`, `content_domain`, `status`)

`POST /admin/knowledge/upload`
- Uploads one PDF (multipart field `file`) and creates `source_document` row(s) with `status='uploaded'` and `sync_published_visible=true` (does **not** enqueue the ingest pipeline)
- Whole-file mode (omit `splits` or send `[]`): optional Form `title` (defaults to PDF basename stem), optional `thumbnail_storage_path` from a prior `POST /admin/files` upload
- Split mode: Form `splits` JSON array of `{start_page, end_page, title, thumbnail_storage_path?}` (1-based inclusive page ranges); each split becomes its own `source_document` with its own `source_document_family_id` and a physically cut PDF object under `source-documents/knowledge/`; the original full PDF is discarded after splitting; top-level `title`/`thumbnail_storage_path` are ignored
- Optional Form `override_duplicates` (boolean, default `false`): when `true`, re-upload even if any produced artifact’s `content_sha256` matches an already-`uploaded` or already-`ingested` `source_document` in the selected tenant. Without override, duplicate content returns `409` Problem Details with `code=duplicate_content` and `conflicts` (no writes). Same-request duplicate digests (e.g. overlapping identical split bytes) return `422`.
- Thumbnail paths (when provided) must already exist in object storage under an allowed prefix; missing/invalid paths return `400`
- Returns `201` with `status: uploaded` and `sources[]` (`source_document_id`, `title`, `source_type`, `stored_path`, optional `thumbnail_storage_path`, optional `start_page`/`end_page`, `status`)

`GET /admin/knowledge/uploaders`
- Lists distinct hierarchy users who uploaded at least one active knowledge document in the selected Spice tenant (`userDetail.country.tenantId`; defaults to `0` when auth is off)
- Knowledge docs are `sync_published_visible=true` and `status != 'retired'`; null `uploaded_by` and Spice ids with no matching hierarchy `users` row in that tenant are omitted
- Unlike `GET /admin/source-documents`, this endpoint is tenant-scoped (filters `source_document.tenant_id` and joins hierarchy `users` in the same tenant)
- Returns `200` with `{ uploaders: [{ id, name }, ...] }` sorted by display name ascending (then id)

`DELETE /admin/knowledge/{source_document_id}`
- Soft-deletes a knowledge source document by setting `status='retired'` (object-storage bytes are kept; cleanup is out of band)
- Only documents with `sync_published_visible=true` may be retired; ingest docs (`sync_published_visible=false`) return `403` with `code=forbidden`
- Missing id returns `404` with `code=source_not_found`; already-retired knowledge docs return `204` (idempotent)
- Retired documents are excluded from `GET /sync/source-documents` even while `sync_published_visible` remains `true`
- Returns `204` No Content

`POST /admin/ingest`
- Queues the v3.3 pipeline (A→B→C→D) per staged source on `platform-celery-worker`
- JSON body: `source_document_ids` (array, min 1 max 10), optional `override_duplicates` (booleans aligned to ids — when `true` on an already-`ingested` id, re-queues ingest in place on the same `source_document` row), optional `ingestion_instructions` (batch-wide steering text for Stage C module identification; sanitized at start and stored on `ingest_batch`), optional `cards_per_module` and `quizzes_per_module` (fixed card/quiz counts per module for this batch; stored on `ingest_batch`; must fall within deployment bounds), plus `assessment_mode` (stored on `ingest_batch`; `read_only` skips post-publish quiz generation); primary language is always the deployment primary locale; `content_domain` is set at upload and is not accepted here. Unknown fields (including removed `fuse_sources` and `skip_merge`) are rejected. Stage D always attempts published-module merge for normal ingest (cross-source fusion drafts skip merge internally). Cross-source fusion runs automatically after all pipelines finish when ≥2 sources are successfully queued; single-source batches skip fusion
- Accepts `source_document` rows in `uploaded` status; also `failed` (re-queue same row) and `ingested` only when `override_duplicates` is `true` for that id; already-`ingested` without override returns `409` Problem Details with `code=duplicate_content` for the whole request (atomic — nothing is queued) when any id is blocked; returns `422` with `code=source_not_uploaded` for other non-queueable states
- When an ingestion run terminates as `failed` or `partially_succeeded`, the linked source document(s) are marked `status='failed'` (fusion runs update every constituent source document; `retired` knowledge rows are unchanged)
- Returns `202` with `status: batch_queued`, top-level `batch_id` + `poll_url` (includes API root prefix, e.g. `/medtronics-api/admin/ingest/batches/{batch_id}`), and `sources[]` (each with `source_document_id`, `run_id`, `title`, `source_type`, `stored_path`, `ingested_at`, and `ingested_by` as `{id, name}` when the starter Spice user resolves to a hierarchy `users` row, else `null`). Stamps `source_document.ingested_by`, `ingest_batch.ingested_by`, and each queued `ingestion_run.ingested_by` with the starter's hierarchy user id for every queued document (including in-place re-ingest); does not change `ingested_at`.
- Eagerly creates an `ingest_batch` (including assessment/cardinality/instructions config) and one `queued` `ingestion_run` per successfully queued source so the poll URL is valid immediately
- Optional figure pipeline (defaults off): set `INGEST_SOURCE_IMAGE_EXTRACTION_ENABLED=true` so Stage A extracts native embedded PNG/JPEG/WebP images from PDF/PPTX/DOCX into object storage (`ingest/figures/...`) + `source_image` rows. When `INGEST_SOURCE_IMAGE_LLM_TEXT_ENABLED=true` (default on), Stage A fills empty/placeholder `source_image.alt_text` with a vision transcription plus short description; identical `content_sha256` reuses a prior usable alt (no second LLM call). Set `INGEST_CARD_IMAGE_ASSIGNMENT_ENABLED=true` (default on) so Stage D drafting passes a catalog of usable alt texts to the card-drafter LLM, which selects relevant images per card; resolved images are written as additive `media` with TipTap image nodes embedded in `body_localized`. Failures are best-effort and do not fail the ingest run. PPTX/DOCX only include true picture embeds (no LibreOffice rasterization). Existing modules and existing `source_image` rows are not backfilled.
- Optional video visual extraction (defaults off): set `INGEST_VIDEO_VISUAL_EXTRACTION_ENABLED=true` so Stage A samples frames (~1 / 30s within each transcript chunk, capped), runs vision extraction, appends `## Visual (t=…)` sections onto transcript chunk markdown, and persists frames as `source_image` rows with `start_ms`/`end_ms`. Soft-fail — transcript Stage A still succeeds if vision fails. Tune with `INGEST_VIDEO_FRAME_INTERVAL_MS` and `INGEST_VIDEO_MAX_FRAMES_PER_DOCUMENT`. Card assignment of those frames uses `INGEST_CARD_IMAGE_ASSIGNMENT_ENABLED`. Audio-only sources are unchanged. Existing videos are not backfilled.

`GET /admin/ingest/batches/{batch_id}`
- Polls tree-shaped progress for the whole ingest batch: per-source nodes (thumbnail → extract → module identify, with per-chunk identify nodes and candidates nested under each chunk via `source_chunk_ids[0]`, each candidate holding `card_draft` + post-publish stages) and optional top-level `fusion` when a multi-source batch ran fusion. Each node includes fixed-catalog `title`/`description`. Chunk children use `key: "chunk"` and `chunk_id` (e.g. `chunk-3`) with their own status/`error`/`error_code`/`error_message`; chunk and identify status roll up from children. Candidates with missing lineage or an unknown chunk id are omitted. Batch status rolls up to `queued` | `running` | `succeeded` | `failed` | `partially_succeeded`. When status is `partially_succeeded`, top-level and per-source `error` objects include a human-readable `message` (and optional `causes`) explaining what failed (e.g. no module candidates, draft failures, post-publish failures); rolled-up tree nodes that are `partially_succeeded` also carry `error.message` when children failed. Top-level `ingested_by` is `{id, name}` soft-joined from `ingest_batch.ingested_by` (null when unset or the hierarchy user row is missing).
- When Stage D finds a similar active module (highest-version published in the family if any, else the highest-version draft), it writes a dual-path pair in **two new families** (not the matched tip's family): **secondary** v1 in its family (LLM-merged cards) and **primary** v1 in its family (current-document cards), both `lifecycle_status=review_pending`, linked to each other and the matched tip. Both enqueue full post-publish; sibling candidates continue. The matched tip stays active until override. If an admin later edits that matched tip (`PUT /admin/modules/{id}` creating a new draft version), every `review_pending` row whose `merge_source_module_id` pointed at the old tip is retargeted to the new tip id in the same write (so override-merge retires the current source). Default `GET /admin/modules` (and `status=review_pending`) hides the `review_pending` secondary so the pair is one list row; filter does not hide a secondary after override (it is `draft`).
- Includes top-level `retry_url` when at least one stage is retryable (includes API root prefix, e.g. `/medtronics-api/admin/ingest/batches/{batch_id}/retry`); `null` when nothing is retryable. POST with no body; the server identifies every retryable failed stage and retries them.

`POST /admin/ingest/modules/{module_id}/override-merge`
- Promotes the secondary dual-path merge module for a **primary** `module_id` (`merge_secondary_module_id` set, status `review_pending`)
- Retires the primary and the matched source module via `retire_module` (not the admin retire cascade); clears the **source** family's `current_published_module_id`; keeps secondary in its own family at its current version, sets it to `draft` with `supersedes_module_id` pointing at the source (does not bump version, re-home `module_family_id`, or set the secondary family's published pointer while draft). Secondary’s cards/quizzes/embeddings/search metadata are kept as-is (no copy).
- Returns `200` with `primary_module_id`, `secondary_module_id`, `source_module_id`, `secondary_lifecycle_status`; `400`/`404`/`409` Problem Details for invalid primary, missing modules, or non-`review_pending` state

`POST /admin/ingest/modules/{module_id}/split-merge`
- Keeps the dual-path **primary** `module_id` (`merge_secondary_module_id` set, status `review_pending`) as `draft` in its own family
- Retires the secondary merge module (`retired_by` from the Spice actor when present); does not mutate the matched source module or any family's `current_published_module_id`; leaves dual-path merge FKs and versions unchanged
- Returns `200` with `primary_module_id`, `secondary_module_id`, `source_module_id` (null when unset), `primary_lifecycle_status`, `secondary_lifecycle_status`; `400`/`404`/`409` Problem Details for invalid primary, missing modules, or non-`review_pending` state

`POST /admin/ingest/batches/{batch_id}/retry`
- Retries every retryable failed stage in the batch with no request body; identifies targets server-side and reuses the per-stage retry path for each. This is the URL returned as poll `retry_url`.
- Returns `202` with `results[]` (each with `run_id`, `stage`, `status` of `retry_queued` or `noop`, optional `candidate_id` / `chunk_id` / `reason`) and `poll_url` (includes API root prefix) when at least one retry was queued; `200` when every result is `noop` or there were no targets; `404` when the batch is missing

`POST /admin/files`
- Upload an admin file asset (object storage)

`GET /admin/files/presigned-url`
- Presigned GET for an admin file object

`POST /admin/modules` and `GET /admin/modules`
- Create and list modules. Create accepts optional `content_domain` (`clinical` | `digital` | `operational`; default `clinical`). List supports optional `content_domain` filter (repeat and/or comma-separate; ANDs with other filters). Module summaries and detail include `content_domain` (`null` on pre-change rows). List supports optional `status` (`draft` | `published` | `retired` | `deactivated` | `review_pending`; default list excludes `retired`, and includes `deactivated` + `review_pending`), optional `chatbot_faqs_only` (`true` | `false`; omit for all), optional `division_id` / `district_id` / `upazila_id` assignee-geography filters (integer hierarchy ids; repeat and/or comma-separate for OR within each dimension; AND across dimensions; matches modules whose family has at least one `module_assignment` to a user in the resolved geography), `limit` (default 50, max 200), `offset` (default 0), `sort_by` (`created_at` | `updated_at` | `published_at` | `activated_at` | `deactivated_at` | `title` | `domain` | `lifecycle_status`; default `published_at`), and `sort_dir` (`asc` | `desc`; default `desc`). Returns a paginated envelope: `{ modules, total_modules, total_pages, limit, offset }`. Module summaries expose `updated_at`, `activated_at`, `deactivated_at`, and `retired_at` lifecycle timestamps, last-actor refs (`created_by`, `published_by`, `activated_by`, `deactivated_by`, `retired_by`), plus optional dual-path merge FKs (`merge_secondary_module_id`, `merge_primary_module_id`, `merge_source_module_id`).

`GET /admin/modules/domains`
- Distinct `module.domain` values for admin filter dropdowns; optional `status` matches the modules list tabs. Omit `status` for All (retired excluded; deactivated + review_pending included), same as `GET /admin/modules`.

`GET /admin/modules/{module_id}`, `PUT /admin/modules/{module_id}`, `DELETE /admin/modules/{module_id}`
- Module CRUD. `PUT` requires `expected_version` (the version of the module row being edited). If that version is stale or another writer already created a newer family tip, returns `409` Problem Details with `code=module_version_conflict` (`expected_version`, `current_version`, `latest_module_id` as extensions); client must `GET` the latest module and retry. Optional `content_domain`, `domain`, and `estimated_minutes` on `PUT` update those fields on the new draft version (omit to copy forward; empty/unnormalizable `domain` → 400). When the body is a **complete content snapshot** (`title`, `description`, `module_json`, `thumbnail_storage_path`, plus quiz as top-level `quiz` or nested `module_json.quiz`) and matches the tip, `PUT` is a no-op and returns the existing `id` / `version` (no new draft). `chatbot_faqs_only`, `content_domain`, `domain`, `estimated_minutes`, gap ids, and `editor_id` are ignored for equality unless explicitly changed. Omitted content fields still create a new version. When a real version bump runs and the edited tip is a dual-path merge source, all `review_pending` modules with `merge_source_module_id` equal to that tip are updated to the new tip id (equality no-ops do not retarget). `DELETE` retires the module (`lifecycle_status=retired`); when the module is a dual-path merge primary (`merge_secondary_module_id` set), the secondary is retired in the same operation. Retiring a secondary alone does not retire the primary. Response is `{ id, lifecycle_status, retired_at }` for the requested module only.

`POST /admin/badges` and `GET /admin/badges`
- Create and list active learner-achievement badges. Optional `sequence` (integer ≥ 1, or null/omitted) is a display-order bucket and must be unique among active badges. List supports optional `domain` (exact), optional `created_by` (exact; repeat and/or comma-separate), optional inclusive `created_from` / `created_to` on `created_at` (422 if from > to), optional `module_title` (case-insensitive substring on linked module primary-locale title; repeat and/or comma-separate; OR across titles), optional `q` (case-insensitive substring on badge name), optional `sort_by` (`created_at` | `sequence`, default `created_at`) and `sort_dir` (`asc` | `desc`, default `desc`; invalid values → 422 `invalid_query`; `sort_by=sequence` always places nulls last), `limit` (default 50, max 200), and `offset` (default 0). Provided filters AND together. Returns `{ badges, total, total_pages, limit, offset }`. Each badge includes `module_ids` and `modules` (`[{ id, title }]` with locale-keyed `title`) for admin display. Soft-deleted badges are excluded. Image assets are uploaded via `POST /admin/files`; the badge stores `image_storage_path` only. `module_ids` may only reference published modules at write time; linked modules need not share the badge domain. Domain is normalized like module taxonomy and must already exist on at least one module; unknown / empty / unnormalizable domain → 400 `badge_domain_invalid`. Admin domain dropdowns use `GET /admin/modules/domains`.

`GET /admin/badges/{badge_id}`, `PUT /admin/badges/{badge_id}`, `DELETE /admin/badges/{badge_id}`
- Badge CRUD. `PUT` replaces the full badge fields and `module_ids` (replace-all). Responses include linked `modules` with localized titles alongside `module_ids`. Optional `sequence` on create/update: omit or null on create leaves unordered (`null`); on update, omit leaves the prior value unchanged, while explicit `null` clears it. Values below 1 → 422 validation error (no upper bound). `DELETE` soft-deletes (`status=deleted`); subsequent GET returns 404 and the badge is omitted from list. Name is unique among active badges.
- Awards: when telemetry processing newly completes a linked module **version** (full quiz-question coverage on that `module.id`), the module-completion worker evaluates active same-tenant badges that include that version and inserts into `chw_badge` (`chw_id`, `badge_id`, `earned_at`, `tenant_id`) if every linked currently published module version is complete. Empty module lists, soft-deleted badges, and zero-quiz linked modules never award. Awards are not revoked when badge modules change or the badge is soft-deleted. There is no learner read API for earned badges yet.

`POST /admin/divisions` and `GET /admin/divisions`
- Create and list tenant-scoped divisions (top of the geographic hierarchy: Division → District → Upazila). List supports optional `q` (case-insensitive substring on `name`), `limit` (default 50, max 200), and `offset` (default 0). Returns `{ divisions, total, total_pages, limit, offset }`. Division `id` is DB-generated (identity).

`GET /admin/divisions/{division_id}`, `PUT /admin/divisions/{division_id}`, `DELETE /admin/divisions/{division_id}`
- Division CRUD. `DELETE` cascades to districts (and their users/upazilas).

`POST /admin/districts` and `GET /admin/districts`
- Create and list tenant-scoped districts under a division. Create/update accept optional `division_id` while backfill is in progress (`district.division_id` is nullable until migration 0083). Responses include `division_id` and `division` (name) when set. List supports optional `division_id`, optional `q` (case-insensitive substring on `name`), `limit` (default 50, max 200), and `offset` (default 0). Returns `{ districts, total, total_pages, limit, offset }`. District `id` is DB-generated (identity).

`GET /admin/districts/{district_id}`, `PUT /admin/districts/{district_id}`, `DELETE /admin/districts/{district_id}`
- District CRUD. `DELETE` cascades to all hierarchy `users` under that district (and their subtrees).

`POST /admin/hierarchy/users` and `GET /admin/hierarchy/users`
- Create and list tenant-scoped hierarchy users at `/admin/hierarchy/users`. Create requires an externally supplied integer `id` (no DB sequence), `name`, `role` (`AREA_MANAGER` | `PO` | `SHASTIYA_KORMI`), `district_id`, `upazila`, and `parent_id` (`null` only for `AREA_MANAGER`). Tree rules: AM → PO → SK, same district and tenant (enforced in app + DB trigger). Responses include derived `division_id` / `division` from the user's district. List supports optional `division_id`, `district_id`, `role`, `parent_id`, `upazila_id` (any linked upazila via `user_upazila`), optional `q` (case-insensitive substring on `name`; ANDs with other filters), plus `limit`/`offset`.

`POST /admin/hierarchy/import`
- Multipart upload (`file`) of a `.csv` or `.xlsx` org-chart that mirrors the caller's selected Spice tenant hierarchy in one atomic transaction. Required columns (aliases allowed for spacing/case): `Division`, `District`, `Upazila`, `AM name`, `AM mHealth Account`, `Rural PO Name`, `PO User_Id`, `Sk Name`, `SK user_id`. Creates/updates geo by name-under-parent and users by external mHealth ids (AM→PO→SK); unions upazilas when the same id appears on multiple rows in one district; hard-rejects cross-district or disagreeing name/role/parent for the same id. Deletes AM/PO/SK users and geo absent from the file (`SUPER_ADMIN` retained). Caps: 5 MiB and 20_000 data rows. Returns `{ divisions, districts, upazilas, users }` each with `{ created, updated, deleted }` counts. Does not create SPICE accounts, dry-run, or async jobs.

`GET /admin/hierarchy/users/{user_id}`, `PUT /admin/hierarchy/users/{user_id}`, `DELETE /admin/hierarchy/users/{user_id}`
- Hierarchy user CRUD. `DELETE` cascades to descendant users. When SPICE auth is enabled, non-`SUPER_USER`/`JOB_USER` principals must exist in the hierarchy `users` table with a role name that exactly matches a SPICE `roles[].name` (`AREA_MANAGER` / `PO` / `SHASTIYA_KORMI` / `SUPER_ADMIN`); missing or mismatched rows return `403 hierarchy_auth_failed`. Missing `SUPER_USER` / `JOB_USER` / `SUPER_ADMIN` principals are auto-provisioned as root `SUPER_ADMIN` rows on authenticate (see Auth section). Coordinate deploy with SPICE role-name rename and hierarchy data import.

`GET /admin/ingestion-runs` and `GET /admin/ingestion-runs/{run_id}`
- List and inspect ingestion runs. List supports optional `status`, optional `q` (case-insensitive substring on `original_filename` or `title`), optional `ingested_by` (hierarchy user id(s); repeat and/or comma-separate), `limit` (default 50, max 200), `offset` (default 0), `sort_by` (`started_at` | `completed_at` | `status` | `document_label`; default `started_at`), and `sort_dir` (`asc` | `desc`; default `desc`). Returns a paginated envelope: `{ runs, total_runs, total_pages, limit, offset }`. Each run (list and detail) includes `ingested_by` as `{id, name}` soft-joined from `ingestion_run.ingested_by` (null when unset or the hierarchy user row is missing). `generated_module_count`, `generated_card_count`, and `generated_quiz_count` are frozen when the run reaches a terminal status after post-publish (and refreshed on sibling pipeline runs when same-batch fusion shares modules); historical runs without a snapshot return `0`. Dual-path `review_pending` secondaries are excluded from the module count.

`GET /admin/source-documents`
- List source documents for admin catalog views (ingest dropdowns, video upload table, knowledge catalog). Optional `status` (`uploaded` | `ingesting` | `ingested` | `failed` | `retired`; omit for all non-retired statuses; repeat and/or comma-separate for multiple; use `status=retired` to list retired only), optional `sync_published_visible` (`true` = knowledge docs, `false` = ingest docs; omit for both), optional `source_type` (`pdf` | `pptx` | `docx` | `audio` | `video`; repeat and/or comma-separate for multiple), optional `q` (case-insensitive substring on `original_filename` or `title`), optional `uploaded_by` (hierarchy user id(s); repeat and/or comma-separate), optional `assigned` (`true` = has at least one document assignment; `false` = unassigned; omit for both), optional `division_id` / `district_id` / `upazila_id` assignee-geography filters (integer hierarchy ids; repeat and/or comma-separate for OR within each dimension; AND across dimensions; matches documents with at least one `document_assignment` to a user in the resolved geography); supports `limit` (default 50, max 200), `offset` (default 0), `sort_by` (`ingested_at` | `title` | `source_type` | `status` | `content_domain` | `original_filename`; default `ingested_at`), and `sort_dir` (`asc` | `desc`; default `desc`). Returns a paginated envelope: `{ source_documents, total_source_documents, total_pages, limit, offset }`. Each row includes `stored_path` (object-storage path for download via existing presign), plus `description`, `thumbnail_storage_path`, and `duration_ms` (audio/video milliseconds; null otherwise) when set. Actor fields `uploaded_by`, `updated_by`, and `ingested_by` are `{id, name}` soft-joins to hierarchy `users` (null when unset or the user row is missing).

`PATCH /admin/source-documents/{source_document_id}`
- Update `title` and/or `description` without re-ingest. Title, when provided, must be non-empty.

`PUT /admin/source-documents/{source_document_id}/thumbnail`
- Replace the source document thumbnail (multipart image: PNG, JPEG, or WebP). Does not re-upload the source file or start ingestion.

`POST /admin/assignments`
- Assign published modules via `user_ids`, `upazila_ids`, `district_ids`, and/or `division_ids`. Each stored row is one assignee. PO `user_ids` assign only that PO unless `expand_po_assignees` is true (then the PO and their direct Shastiya Kormi children). `upazila_ids` expand to PO/SK users in that upazila (Area Managers excluded). `district_ids` and `division_ids` expand to all hierarchy users in that geography, including Area Managers.

`GET /admin/assignments/{module_id}/users`
- List hierarchy users with a direct module assignment row for the given module. Returns `{ module_id, users }` where each user is a hierarchy `UserResponse` (name, role, district, upazilas).

`PUT /admin/assignments/{module_id}/users`
- Replace the full assignee set for a module via `user_ids`, `upazila_ids`, `district_ids`, and/or `division_ids` (same PO expand / upazila / district / division rules as create, including optional `expand_po_assignees`). Adds missing rows, removes rows no longer in the resolved set, and preserves existing rows for unchanged assignees. Empty or omitted `user_ids`, `upazila_ids`, `district_ids`, and `division_ids` clears all assignees. Returns `{ added_count, removed_count, assignment_ids }`.

`POST /admin/document-assignments`
- Assign any uploaded source document via `source_document_id` plus `user_ids`, `upazila_ids`, `district_ids`, and/or `division_ids`. Uses the same PO expand / upazila / district / division rules as module assignment (including optional `expand_po_assignees`). No status or `source_type` checks. Returns `{ assigned_count, assignment_ids }`. Document sync for assigned docs is not yet wired.

`GET /admin/document-assignments/{source_document_id}/users`
- List hierarchy users with a direct document assignment row for the given source document. Returns `{ source_document_id, users }` where each user is a hierarchy `UserResponse`.

`PUT /admin/document-assignments/{source_document_id}/users`
- Replace the full assignee set for a source document via `user_ids`, `upazila_ids`, `district_ids`, and/or `division_ids` (same PO expand / upazila / district / division rules as create, including optional `expand_po_assignees`). Adds missing rows, removes rows no longer in the resolved set, and preserves existing rows for unchanged assignees. Empty or omitted `user_ids`, `upazila_ids`, `district_ids`, and `division_ids` clears all assignees. Returns `{ added_count, removed_count, assignment_ids }`.


#### Dashboard-facing

`GET /dashboard/digital-help-modules`

`GET /dashboard/digital-help-modules/{module_id}/questions`

`GET /dashboard/digital-help-modules/{module_id}/requests`

`GET /dashboard/module-creation-suggestions`

`GET /dashboard/module-creation-suggestions/{suggestion_id}`

`GET /dashboard/module-demand-summary`

`GET /dashboard/team-activity`

`GET /dashboard/team-activity/users/{user_id}/questions`

`GET /dashboard/published-module-completions`

`GET /dashboard/document-usage`

Current state:
- these routes are part of the canonical API surface
- **ClickHouse-backed response timestamps** (`last_asked_at`, `requested_at`, document `last_viewed_at` / `viewed_at`, module-creation evidence `last_seen_at`) are device-local wall clocks from telemetry `timestamp_local`. Date-range filters (`from`/`to`, `from_date`/`to_date`) and result ordering remain UTC (`event_date` / `timestamp_utc`). Postgres fields (`published_at`, `completed_at`, suggestion `computed_at`) and team-activity `last_chat_at` / `last_active_at` (MV calendar dates) are unchanged. Existing envs that already have `unattributed_module_demand_events` need `ALTER TABLE ... ADD COLUMN timestamp_local DateTime64(3)` and recreate the MV so new inserts populate local times (raw `coaching_events` fallback already has the column).
- **Shared optional geography filters:** all dashboard routes accept optional `division_id`, `district_id`, and `upazila_id` query params (integer hierarchy ids; repeat and/or comma-separate for OR within each dimension; AND across dimensions). When set, metrics count only users assigned to that division, district, and/or upazila; filters compose with hierarchy scope and never widen visibility. Empty intersection → 200 with empty/zero metrics. Document-usage documents the canonical matching rules below.
- Digital-help and module-creation-suggestion reads are hierarchy-scoped: `AREA_MANAGER` sees descendant POs and their SKs (not self); `PO` sees child SKs (not self); `SHASTIYA_KORMI` sees self only; platform admins and auth-off remain unrestricted. Null `chw_id` / null evidence `sample_chw_id` are excluded for scoped viewers. Document-usage keeps include-self semantics separately.
- Optional `view=po|sk` on digital-help list/questions/requests and module-creation-suggestion list/detail: omit for all roles (default). When set, `SUPER_ADMIN` and `AREA_MANAGER` (Spice auth on) narrow visible actors to PROGRAM_ORGANIZER (`PO`) or `SHASTIYA_KORMI` within existing hierarchy + geography scope; `PO`, `SK`, and auth-off ignore the param. Empty intersection → 200 with empty/zero metrics (detail with no in-scope evidence → 404 as today).
- `GET /dashboard/digital-help-modules` ranks modules by combined `digital_help_used` + `module_requested` event volume over required `from_date`/`to_date` (UTC inclusive), keyed on concrete `module_id` (events without `module_id` ignored, including free-text requests; no family roll-up). Each item exposes `digital_help_count` and `module_requested_count`; response totals are `total_digital_help` and `total_module_requested`. Enriched with module titles from PostgreSQL; supports `limit` (default 20) and `offset` (default 0) pagination with `total_modules` in the response; `from_date > to_date` → 422
- `GET /dashboard/digital-help-modules/{module_id}/questions` uses the same auth/tenant model as the list (`get_selected_tenant_id` / authenticate `userDetail.country.tenantId`). Required `from_date`/`to_date`, `limit`/`offset` (default 50 / max 200). Returns deduplicated chatbot questions for that concrete `module_id` from `digital_help_used` (`payload_json.question`, fallback `query`): newest-first by latest occurrence, with `occurrence_count`, latest raw `question` text, and `asked_by` (`user_id`, name, role, division/district/upazila from the org map) for the CHW who asked most recently; events with null `chw_id` are omitted; blank question text omitted; `title` enriched from PostgreSQL when present (null if unknown). Empty window / unknown module → 200 with empty `questions`
- `GET /dashboard/digital-help-modules/{module_id}/requests` uses the same auth/tenant model. Required `from_date`/`to_date`, `limit`/`offset` (default 50 / max 200). Returns paginated individual `module_requested` events for that concrete `module_id` only (free-text / `requested_module_name`-only events without `module_id` are not counted), newest-first, each with `requested_at`, optional `reason`, and `requested_by` user summary; events with null `chw_id` are omitted; includes `title` when present and envelope `total_requests` / `total_pages`
- `GET /dashboard/module-creation-suggestions` lists daily LLM suggestions for modules to create next, inferred from unattributed `digital_help_used` (no `module_id`) and free-text `module_requested` events. Required `from_date`/`to_date`, optional `limit`/`offset` (default 20). Same dashboard tenant auth and hierarchy visibility: a suggestion appears only if it has evidence whose `sample_chw_id` is in-scope; `question_count` / `request_count` / `evidence_count` are recomputed from in-scope evidence while tenant-wide `rank` is preserved. Items may be `matched_draft` (existing draft `module_id`) or `proposed_topic`. Populated by Celery beat `platform.refresh_module_creation_suggestions` (prior UTC day; still tenant-wide precompute)
- `GET /dashboard/module-creation-suggestions/{suggestion_id}` returns one suggestion with its evidence: deduped chat `questions` and free-text `requests`, filtered to in-scope evidence for hierarchy viewers; each evidence item includes `prompted_by` user summary (most recent asker when deduped). Wrong tenant / unknown id / no in-scope evidence → 404
- `GET /dashboard/module-demand-summary` returns a structured JSON summary for required `from_date`/`to_date` (UTC inclusive), composed from hierarchy-scoped digital-help module usage and module-creation suggestions. Response fields: `title` (`Insights from Module Usage`), `date_label` (English date line, e.g. `Aug 1–17, 2026`), `narrative` (leverage-ordered recommendation paragraph when demand exists), `empty_message` (no-demand sentence when all volumes are zero; `narrative` is then null), and `demand_pattern[]` (ordered items with `bucket`, `title`, and `description`). Buckets are **Assign** (`total_digital_help + total_module_requested`), **Publish** (matched-draft `request_count + question_count`), and **Create** (proposed-topic and other kinds, same counts); they are sorted by full-window volume (ties Assign > Publish > Create) and empty buckets are omitted. Optional `top_limit` (default 10, max 50) is accepted for compatibility and is not used for scoring. Same tenant auth and CHW visibility as the digital-help and module-creation-suggestion list routes (`include_self=false` for hierarchy viewers). ClickHouse failures → 502; empty window → 200 with `empty_message` set and `demand_pattern: []`
- `GET /dashboard/team-activity` is hierarchy-aware under the `dashboard` prefix. Query: `from_date`, `to_date` (UTC inclusive), `limit`, `offset`, optional `user_id` (no `po_user_id`), optional `depth` (default `0`, max `2`), optional `q` (case-insensitive substring on current-level member `name`; omit or whitespace → no name filter; ANDs with other filters), optional `sort_by` (`name` | `chatbot_engagement` | `module_completion` | `performance_status`; default `name`) and `sort_dir` (`asc` | `desc`; default `asc`; invalid values → 422 `invalid_query`). Returns one level at a time as flat `members[]` (each with `role`, `can_drill_down`, and `performance_status`). **Assigned modules** in this route are live `module_assignment` rows whose `assigned_at` falls in the request window (unassign deletes history, so revoked assignments disappear); FAQ-only modules are excluded. An assigned module counts as completed in range only when `chw_module_completion.completed_at` is in the same window and `latest_completed_module_id` equals that concrete `module_id`. **`summary.users_completed_module`** (envelope and AM/PO member nested `summary`) counts SKs with at least one in-window assignment who completed **every** such assignment in the window (0 assigned → not counted). Member `has_completed_module_in_range` remains **any** in-window assigned module completed (used for SK `sort_by=module_completion`). **`performance_status`:** **SK** — `responsive_assigned_modules / assigned_modules >= 0.60` in the date window, where responsive means any `module_card_viewed`, `module_quiz_viewed`, or `module_quiz_attempted` event for that assigned `module_id` (0 assigned → `at_risk`); **PO** — more than 60% of descendant SKs are `on_track`; **AM** — more than 60% of direct child POs are `on_track`. Responsive module IDs are read from `coaching_events` (in addition to MVs used for activity/chatbot metrics). **Sort** applies after `q`, then `limit`/`offset` page it. `sort_by=performance_status` with `sort_dir=asc` puts `at_risk` first (ties: `name`, `user_id`). `sort_by=name`: `asc` is A–Z, `desc` is Z–A; ties use `user_id`. Metric `sort_dir=asc` is the product-natural order; `desc` reverses the primary key only, then `name` / `user_id`. **`chatbot_engagement`:** AM/PO use `summary.users_chatbot_engaged` low-to-high; SK rows put `is_chatbot_engaged=false` first. **`module_completion`:** AM/PO use `summary.users_completed_module` low-to-high; SK rows put `has_completed_module_in_range=false` first. Empty AM/PO subtrees (`summary.total_users=0`) sort as zeros. **Default focus (`depth=0`):** platform Admin / auth-off → all tenant `AREA_MANAGER`s; Area Manager → direct child POs; PO device → direct child SKs. **Skip-level (`depth`):** relative to the effective focus (caller default or `user_id`) — Admin `depth=1` → all POs under those AMs (orphan POs excluded); Admin `depth=2` → all SKs under those AMs' POs; AM `depth=1` → all SKs under that AM. Illegal `depth` for the focus role (e.g. AM `depth=2`, PO `depth≥1`) → 422. **Drill:** `?user_id=<descendant>` focuses on that user (must be in the caller's subtree, else 403) and composes with `depth` (e.g. Admin + `user_id=<AM>` + `depth=1` → SKs under that AM); AM focus → POs at `depth=0`; PO focus → SKs at `depth=0`; SK focus → empty `members` with `summary`/`total_users` for that single SK (`depth>0` → 422). AM/PO row metrics roll up from descendant SKs. Each AM/PO member includes a nested `summary` over descendant SKs (same fields as the envelope; empty subtree → zeros); SK members have `summary` null. `focus_user_id` echoes the query when set, otherwise null. `limit`/`offset`/`total_pages` page current-level `members` (`total_members` is post-`q`); `summary.*` and `total_users` count SKs under the effective focus (orphan SKs with no PO under an AM tree excluded) and are not narrowed by `q`. Returns assigned module completion, chatbot usage by module, and per-member `refreshers_generated` / `refreshers_completed`. ClickHouse reads use MVs `chw_daily_summary` and `chw_digital_help_daily` for activity/chatbot metrics; refresher counts are folded in-app from ordered `coaching_events` rows with `event_type = module_quiz_attempted` in the date window (incorrect opens a refresher per `quiz_id`, subsequent correct closes it; window-only pairing). Per-member `last_chat_at` and `last_active_at` are all-time latest activity dates (UTC midnight) from those MVs.
- `GET /dashboard/team-activity/users/{user_id}/questions` is hierarchy-aware like the list route (no `po_user_id`). Same caller gate via `resolve_team_activity_scope`: PO → own subtree; Area Manager → descendants; Admin / auth-off → unrestricted within the tenant org map. Required `from_date`/`to_date`, `limit`/`offset` (default 50 / max 200). Returns deduplicated chatbot questions for one visible member from `digital_help_used` (`payload_json.question`, fallback `query`): newest-first by latest occurrence, with `occurrence_count` and latest raw `question` text. Path `user_id` must be the caller or a descendant (unrestricted: any org-map user); unknown / out-of-subtree → 403. Blank question text is omitted.
- `GET /dashboard/published-module-completions` is Admin / Area Manager only (device principals including organizer POs → 403 via `resolve_published_module_completions_scope`; auth-off → unrestricted). Required `from_date`/`to_date` (UTC inclusive; `from_date > to_date` → 422), `limit`/`offset` (default 20 / max 200). Lists currently `lifecycle_status=published` non-FAQ modules whose `published_at` falls in the window, newest-first. Each item includes `module_id`, `module_family_id`, `title`, `published_at`, `completed_sk_count` (distinct descendant SKs with `chw_module_completion.completed_at` in the same window for that family), `assigned_sk_count` (distinct descendant SKs assigned to that module family within scope), and `total_descendant_sk_count` (all SKs under Admin tenant tree / AM subtree via `sks_under_focus`; same on every row; also on the envelope). Completions are family-grained: multiple published versions of the same family in range share `completed_sk_count`. Zero-completion modules are included. Postgres only (no ClickHouse).
- `GET /dashboard/document-usage` aggregates `document_viewed` telemetry via the `document_view_daily` MV and raw `coaching_events` into one response (KPIs, per-document rows, event drill-down). Tenant from authenticate `userDetail.country.tenantId` via `get_selected_tenant_id` (no query `tenant_id`). Shared filters: `from`/`to`, `division_id`, `district_id`, `upazila_id` (integer hierarchy ids; repeat/comma-separate OR within dimension; AND across dimensions), optional `user_id` (hierarchy focus like team-activity: out-of-subtree → 403; PO → that PO + child SKs; AM → AM + descendants; SK → that user), `document_id`, optional `q` (case-insensitive substring on source-document `title` via Postgres; omit or whitespace → no title filter; ANDs with other filters and narrows `documents[]` / `total_document_rows` only — KPIs, `top_documents`, and events stay unfiltered by `q`). Geography filters resolve via the org user map. Viewer scope is the authenticated principal (PO/AM include-self; platform admins / auth-off unrestricted). The MV is defined in `infra/clickhouse/init.sql` (drop legacy `document_open_daily` if present on existing envs).

#### Operational

`GET /ready`
- Readiness probe: PostgreSQL, Redis, ClickHouse, ai-runtime (including provider alignment), and object storage

### AI Runtime

#### Internal-only

`POST /internal/generate/{generation_type}`
- Canonical private generation endpoint
- Supported generation types are validated against the shared enum
- This intentionally consolidates counselling, IT help, extraction, and quiz generation into one internal route

`POST /internal/embed`
- Private embedding endpoint used by platform ingestion/retrieval flows

`GET /health`
- Basic runtime liveness endpoint

## Request Flows

### Coaching RAG

1. SDK calls `POST /coaching/rag-query`
2. Platform resolves `response_language` (defaults to deployment primary locale; may also be any locale in `DEPLOYMENT_ADDITIONAL_LOCALES`). Greeting / chit-chat / crisis-looking messages may take an early `coaching_chat_route` path and return without retrieval
3. Otherwise platform embeds the question via `POST /internal/embed` on `ai-runtime`
4. Platform retrieves similar published modules through `VectorStore.search` (pgvector adapter today)
5. Platform builds a grounded prompt and calls `POST /internal/generate/coaching_rag`
6. Platform returns the JSON answer with source-document attribution

### Telemetry

1. SDK calls `POST /telemetry/events`
2. Platform validates and translates telemetry rows
3. Platform writes accepted telemetry to ClickHouse
4. Platform queues module-completion and gap-update jobs to Redis
5. Worker consumes queued jobs and updates PostgreSQL state

### Sync

1. SDK calls `GET /sync/modules?since=...` for published modules and quizzes (includes `assigned_module_ids` and `requested_modules` for the authenticated CHW)
2. SDK calls `GET /sync/source-documents?since=...` for presigned downloads of module-linked documents (delta) and the CHW's assigned documents (full snapshot)
3. SDK calls `GET /sync/video-progress?since=...` for delta watch progress on still-assigned videos
4. SDK calls `GET /sync/triggers?since=...` and `GET /sync/gaps?since=...` as needed
5. SDK calls `GET /sync/chat-faqs?since=...` for bilingual FAQ suggestion chips (clustered + LLM-synthesized nightly)
6. SDK calls `GET /sync/config` for threshold/config values

## Current Implementation Status

### Implemented

- monorepo layout with `platform`, `ai-runtime`, `contracts`, and `foundation`
- single Alembic chain under `infra/alembic`
- v3.3 module-centric sync (`/sync/modules`, `/sync/triggers`, `/sync/gaps`, `/sync/chat-faqs`, presign batches)
- coaching RAG via platform → internal AI runtime
- telemetry ingest with ClickHouse writes
- Redis-backed Celery workers for:
  - v3.3 ingest pipeline (A→B→C→D) and cross-source fusion
  - post-publish quiz, embedding, and gap classification
  - module-completion telemetry processing
- morning-card selection with config-driven `morning_cards_max`
- SPICE auth middleware with DB role→route authorization (when `SPICE_AUTH_ENABLED=true`)
- `/ready` readiness probe with dependency checks

### Intentionally Designed This Way

- `ai-runtime` uses one generic internal generation route:
  - `POST /internal/generate/{generation_type}`
- This is an intentional consolidation, not route drift

### Not Yet Fully Implemented

- legacy device routes: `POST /coaching/counselling`, `POST /coaching/quiz-answer`, `POST /coaching/it-help`
- legacy sync route: `GET /scenarios/sync?since_version=N` (replaced by `GET /sync/modules?since=...`)
- legacy admin scenario/document routes under `/admin/scenarios/*` and `/admin/documents/*`
- full config-management admin endpoints beyond threshold sync
- richer dashboard and analytics materialization flows

## Standards Decisions

- No public generic chat or unrestricted RAG endpoints are exposed
- The SDK talks only to `platform-api`
- `ai-runtime` is private and token-protected
- Platform is the system of record
- Legacy drifted route aliases are not part of the API contract
- The workspace is managed with `uv`, and `uv.lock` should be committed

## Local Development

### Prerequisites (first-run)

```bash
cp .env.example .env           # then fill GOOGLE_API_KEY
uv sync --locked --all-packages --group dev
```

Without `.env`, `docker compose` fails at parse time because `GOOGLE_API_KEY` is declared required. See `docs/SETUP_TROUBLESHOOTING.md` for other known failures.

### Pre-commit

After syncing dev dependencies, install git hooks once:

```bash
uv run pre-commit install
```

Hooks run ruff (lint + format), Pyright type checking (on Python changes), and basic file hygiene on each commit. To check the whole repo without committing:

```bash
uv run pre-commit run --all-files
```

### Environment

### Run services

Platform API:

```bash
uv run uvicorn platform_service.main:app --host 0.0.0.0 --port 8000
```

Platform worker:

```bash
uv run python -m platform_service.workers.main
```

AI runtime:

```bash
uv run uvicorn ai_runtime.main:app --host 0.0.0.0 --port 8001
```

### Run with Docker Compose

1. Create a root `.env` file (or export variables in your shell) and set:
   - `GOOGLE_API_KEY` (required for `ai-runtime`; `GEMINI_API_KEY` is accepted as fallback)
   - `AI_RUNTIME_TOKEN` (optional, defaults to `dev-internal-token`)
   - `APP_ENV` (optional, defaults to `development`)
2. Start the stack:

```bash
docker compose up --build
```

Expected compose behavior:
- `migrate` runs once and exits with code `0`
- `clickhouse-init` runs once and exits with code `0`
- `db`, `redis`, `clickhouse`, `ai-runtime`, and `platform-api` are running
- `platform-celery-worker` and `platform-celery-beat` are running

Quick verification:

```bash
docker compose ps
curl -fsS http://localhost:8000/medtronics-api/ready
curl -fsS http://localhost:8001/health
```

### Migrations

Run Alembic as a separate step:

```bash
uv run alembic -c infra/alembic.ini upgrade head
```

Migrations should not be auto-run by application startup.

## Next Recommended Work

1. Add rate limiting on device-plane routes.
3. Add sync pagination for large module catalogs.
4. Add remaining planned admin config-management flows.
5. Extend CI with type-checking beyond ruff (pyright/mypy) where practical.
