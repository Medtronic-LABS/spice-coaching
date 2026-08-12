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

Callers must obtain JWTs with the correct SPICE login client: admin web uses `client: web` (roles with `suiteAccessName: admin`); the Android SDK uses `client: mob` (roles with `suiteAccessName: mob`). Platform forwards the `client` header to `/authenticate` but authorization is based on roles embedded in the token.

### Authorization (three planes)

When SPICE auth is enabled, routes are split into **admin**, **device**, and **shared** planes (prefixes configurable via `SPICE_ADMIN_PATH_PREFIXES`, `SPICE_DEVICE_PATH_PREFIXES`, and `SPICE_SHARED_PATH_PREFIXES`):

| Plane | Path prefixes (under `API_ROOT_PATH`) | Who may call |
|-------|----------------------------------------|--------------|
| Admin | `admin` | Admin principals (`isSuperUser`, admin-management role names, or `suiteAccessName == admin`). `client: mob` is denied on this plane. |
| Device | `telemetry`, `sync`, `morning`, `coaching` | `isSuperUser`, `isJobUser`, or any role with `suiteAccessName == mob` |
| Shared | `dashboard` | Admin principals **or** device organizers (PO with `suiteAccessName == mob`). `client: mob` is allowed. SK/CHW and other non-PO mob users are denied at middleware. |

Admin and device access remains **strictly partitioned**: an admin principal cannot call device routes and vice versa, except `SUPER_USER` which may use both. The shared plane is additive so web admin and mobile AM/PO can all use `/dashboard/*`. Handler-level hierarchy scoping for dashboard analytics is unchanged. Violations return `403` with `insufficient role for this API`.

Admin routes (including ingest, `POST /admin/ingest`) require **all** of: a valid SPICE token and admin-plane authorization when SPICE auth is enabled.

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
- Module card metadata remains on `GET /sync/modules`; this endpoint is the download channel for linked and assigned documents

`GET /sync/badges`
- Returns available tenant badges (`available_badges`) and earned badges (`earned_badges`) for the authenticated CHW (full snapshot; includes image presigned URLs and linked `module_ids`)

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
- Uploads one or more source files (multipart field `files`, max 10) to object storage and creates `source_document` rows with `status='uploaded'` (pipeline not queued; always `sync_published_visible=false`)
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
- JSON body: `source_document_ids` (array, min 1 max 10), optional `override_duplicates` (booleans aligned to ids — when `true` on an already-`ingested` id, clones a new `source_document` row from stored bytes before queueing), optional `ingestion_instructions` (batch-wide steering text for Stage C module identification; sanitized at start and stored on `ingest_batch`), optional `cards_per_module` and `quizzes_per_module` (fixed card/quiz counts per module for this batch; stored on `ingest_batch`; must fall within deployment bounds), plus `assessment_mode` (stored on `ingest_batch`; `read_only` skips post-publish quiz generation); primary language is always the deployment primary locale; `content_domain` is set at upload and is not accepted here. Unknown fields (including removed `fuse_sources` and `skip_merge`) are rejected. Stage D always attempts published-module merge for normal ingest (cross-source fusion drafts skip merge internally). Cross-source fusion runs automatically after all pipelines finish when ≥2 sources are successfully queued; single-source batches skip fusion
- Accepts `source_document` rows in `uploaded` status; also `failed` (re-queue same row) and `ingested` only when `override_duplicates` is `true` for that id; already-`ingested` without override returns `409` Problem Details with `code=duplicate_content` for the whole request (atomic — nothing is queued) when any id is blocked; returns `422` with `code=source_not_uploaded` for other non-queueable states
- Returns `202` with `status: batch_queued`, top-level `batch_id` + `poll_url` (includes API root prefix, e.g. `/medtronics-api/admin/ingest/batches/{batch_id}`), and `sources[]` (each with `source_document_id`, `run_id`, `title`, `source_type`, `stored_path`)
- Eagerly creates an `ingest_batch` (including assessment/cardinality/instructions config) and one `queued` `ingestion_run` per successfully queued source so the poll URL is valid immediately
- Optional figure pipeline (defaults off): set `INGEST_SOURCE_IMAGE_EXTRACTION_ENABLED=true` so Stage A extracts native embedded PNG/JPEG/WebP images from PDF/PPTX/DOCX into object storage (`ingest/figures/...`) + `source_image` rows; set `INGEST_CARD_IMAGE_ASSIGNMENT_ENABLED=true` so Stage D assigns those images onto cards as additive `media` (proximity pages from `source_block_ids`, then embedding re-rank). Failures are best-effort and do not fail the ingest run. PPTX/DOCX only include true picture embeds (no LibreOffice rasterization). Existing modules are not backfilled.
- Optional video visual extraction (defaults off): set `INGEST_VIDEO_VISUAL_EXTRACTION_ENABLED=true` so Stage A samples frames (~1 / 30s within each transcript chunk, capped), runs vision extraction, appends `## Visual (t=…)` sections onto transcript chunk markdown, and persists frames as `source_image` rows with `start_ms`/`end_ms`. Soft-fail — transcript Stage A still succeeds if vision fails. Tune with `INGEST_VIDEO_FRAME_INTERVAL_MS` and `INGEST_VIDEO_MAX_FRAMES_PER_DOCUMENT`. Card assignment of those frames still uses `INGEST_CARD_IMAGE_ASSIGNMENT_ENABLED`. Audio-only sources are unchanged. Existing videos are not backfilled.

`GET /admin/ingest/batches/{batch_id}`
- Polls tree-shaped progress for the whole ingest batch: per-source nodes (thumbnail → extract → module identify, with per-chunk identify nodes and candidates nested under each chunk via `source_chunk_ids[0]`, each candidate holding `card_draft` + post-publish stages) and optional top-level `fusion` when a multi-source batch ran fusion. Each node includes fixed-catalog `title`/`description`. Chunk children use `key: "chunk"` and `chunk_id` (e.g. `chunk-3`) with their own status/`error`/`error_code`/`error_message`; chunk and identify status roll up from children. Candidates with missing lineage or an unknown chunk id are omitted. Batch status rolls up to `queued` | `running` | `succeeded` | `failed` | `partially_succeeded`.
- When Stage D finds a similar active module, it writes a dual-path pair in the matched family without parking: **primary** (current-document cards) and **secondary** (LLM-merged cards), both `lifecycle_status=review_pending`, linked to each other and the matched tip. Both enqueue full post-publish; sibling candidates continue. The matched tip stays active until override. Pairs appear in the default module list; filter with `GET /admin/modules?status=review_pending` for review-pending only.
- Includes top-level `retry_url` when at least one stage is retryable (includes API root prefix, e.g. `/medtronics-api/admin/ingest/batches/{batch_id}/retry`); `null` when nothing is retryable. POST with no body; the server identifies every retryable failed stage and retries them.

`POST /admin/ingest/modules/{module_id}/override-merge`
- Promotes the secondary dual-path merge module for a **primary** `module_id` (`merge_secondary_module_id` set, status `review_pending`)
- Retires the primary and the matched source module; sets secondary to `draft` with `supersedes_module_id` pointing at the source; advances secondary `version` in place to family tip (`max(version)+1`) and points `module_family.current_published_module_id` at the secondary so default `GET /admin/modules?source_document_id=…&latest_version_only=true` includes it. Secondary’s cards/quizzes/embeddings/search metadata are kept as-is (no copy).
- Returns `200` with `primary_module_id`, `secondary_module_id`, `source_module_id`, `secondary_lifecycle_status`; `400`/`404`/`409` Problem Details for invalid primary, missing modules, non-`review_pending` state, or `module_version_conflict` if the in-place version bump collides

`POST /admin/ingest/batches/{batch_id}/retry`
- Retries every retryable failed stage in the batch with no request body; identifies targets server-side and reuses the per-stage retry path for each. This is the URL returned as poll `retry_url`.
- Returns `202` with `results[]` (each with `run_id`, `stage`, `status` of `retry_queued` or `noop`, optional `candidate_id` / `chunk_id` / `reason`) and `poll_url` (includes API root prefix) when at least one retry was queued; `200` when every result is `noop` or there were no targets; `404` when the batch is missing

`POST /admin/files`
- Upload an admin file asset (object storage)

`GET /admin/files/presigned-url`
- Presigned GET for an admin file object

`POST /admin/modules` and `GET /admin/modules`
- Create and list modules. List supports optional `status` (`draft` | `published` | `retired` | `deactivated` | `review_pending`; default list excludes `retired` and `deactivated`, and includes `review_pending`), optional `chatbot_faqs_only` (`true` | `false`; omit for all), `limit` (default 50, max 200), `offset` (default 0), `sort_by` (`created_at` | `published_at` | `activated_at` | `last_deactivated_at` | `title` | `domain` | `lifecycle_status`; default `published_at`), and `sort_dir` (`asc` | `desc`; default `desc`). Returns a paginated envelope: `{ modules, total_modules, total_pages, limit, offset }`. Module summaries include optional dual-path merge FKs (`merge_secondary_module_id`, `merge_primary_module_id`, `merge_source_module_id`).

`GET /admin/modules/domains`
- Distinct `module.domain` values for admin filter dropdowns; optional `status` matches the modules list tabs

`GET /admin/modules/{module_id}`, `PUT /admin/modules/{module_id}`, `DELETE /admin/modules/{module_id}`
- Module CRUD. `PUT` requires `expected_version` (the version of the module row being edited). If that version is stale or another writer already created a newer family tip, returns `409` Problem Details with `code=module_version_conflict` (`expected_version`, `current_version`, `latest_module_id` as extensions); client must `GET` the latest module and retry. When the body is a **complete content snapshot** (`title`, `description`, `module_json`, `thumbnail_storage_path`, plus quiz as top-level `quiz` or nested `module_json.quiz`) and matches the tip, `PUT` is a no-op and returns the existing `id` / `version` (no new draft). `chatbot_faqs_only`, gap ids, and `editor_id` are ignored for equality. Omitted content fields still create a new version. `DELETE` retires the module (`lifecycle_status=retired`); when the module is a dual-path merge primary (`merge_secondary_module_id` set), the secondary is retired in the same operation. Retiring a secondary alone does not retire the primary. Response is `{ id, lifecycle_status, deprecated_at }` for the requested module only.

`POST /admin/badges` and `GET /admin/badges`
- Create and list active learner-achievement badges. Optional `sequence` (integer ≥ 1, or null/omitted) is a display-order bucket and must be unique among active badges. List supports optional `domain` (exact), optional `created_by` (exact; repeat and/or comma-separate), optional inclusive `created_from` / `created_to` on `created_at` (422 if from > to), optional `module_title` (case-insensitive substring on linked module primary-locale title; repeat and/or comma-separate; OR across titles), optional `q` (case-insensitive substring on badge name), optional `sort_by` (`created_at` | `sequence`, default `created_at`) and `sort_dir` (`asc` | `desc`, default `desc`; invalid values → 422 `invalid_query`; `sort_by=sequence` always places nulls last), `limit` (default 50, max 200), and `offset` (default 0). Provided filters AND together. Returns `{ badges, total, total_pages, limit, offset }`. Each badge includes `module_ids` and `modules` (`[{ id, title }]` with locale-keyed `title`) for admin display. Soft-deleted badges are excluded. Image assets are uploaded via `POST /admin/files`; the badge stores `image_storage_path` only. `module_ids` may only reference published modules at write time; linked modules need not share the badge domain. Domain is normalized like module taxonomy and must already exist on at least one module; unknown / empty / unnormalizable domain → 400 `badge_domain_invalid`. Admin domain dropdowns use `GET /admin/modules/domains`.

`GET /admin/badges/{badge_id}`, `PUT /admin/badges/{badge_id}`, `DELETE /admin/badges/{badge_id}`
- Badge CRUD. `PUT` replaces the full badge fields and `module_ids` (replace-all). Responses include linked `modules` with localized titles alongside `module_ids`. Optional `sequence` on create/update: omit or null on create leaves unordered (`null`); on update, omit leaves the prior value unchanged, while explicit `null` clears it. Values below 1 → 422 validation error (no upper bound). `DELETE` soft-deletes (`status=deleted`); subsequent GET returns 404 and the badge is omitted from list. Name is unique among active badges.
- Awards: when telemetry processing newly completes a linked module **version** (full quiz-question coverage on that `module.id`), the module-completion worker evaluates active same-tenant badges that include that version and inserts into `chw_badge` (`chw_id`, `badge_id`, `earned_at`, `tenant_id`) if every linked currently published module version is complete. Empty module lists, soft-deleted badges, and zero-quiz linked modules never award. Awards are not revoked when badge modules change or the badge is soft-deleted. There is no learner read API for earned badges yet.

`POST /admin/districts` and `GET /admin/districts`
- Create and list tenant-scoped districts (top of the AM → PO → SK org hierarchy). List supports optional `q` (case-insensitive substring on `name`), `limit` (default 50, max 200), and `offset` (default 0). Returns `{ districts, total, total_pages, limit, offset }`. District `id` is DB-generated (identity).

`GET /admin/districts/{district_id}`, `PUT /admin/districts/{district_id}`, `DELETE /admin/districts/{district_id}`
- District CRUD. `DELETE` cascades to all hierarchy `users` under that district (and their subtrees).

`POST /admin/hierarchy/users` and `GET /admin/hierarchy/users`
- Create and list tenant-scoped hierarchy users at `/admin/hierarchy/users`. Create requires an externally supplied integer `id` (no DB sequence), `name`, `role` (`AREA_MANAGER` | `PO` | `SHASTIYA_KORMI`), `district_id`, `upazila`, and `parent_id` (`null` only for `AREA_MANAGER`). Tree rules: AM → PO → SK, same district and tenant (enforced in app + DB trigger). List supports optional `district_id`, `role`, `parent_id`, `upazila_id` (any linked upazila via `user_upazila`), optional `q` (case-insensitive substring on `name`; ANDs with other filters), plus `limit`/`offset`.

`GET /admin/hierarchy/users/{user_id}`, `PUT /admin/hierarchy/users/{user_id}`, `DELETE /admin/hierarchy/users/{user_id}`
- Hierarchy user CRUD. `DELETE` cascades to descendant users. When SPICE auth is enabled, non-`SUPER_USER`/`JOB_USER` principals must exist in the hierarchy `users` table with a role name that exactly matches a SPICE `roles[].name` (`AREA_MANAGER` / `PO` / `SHASTIYA_KORMI`); missing or mismatched rows return `403 hierarchy_auth_failed`. Coordinate deploy with SPICE role-name rename and hierarchy data import.

`GET /admin/ingestion-runs` and `GET /admin/ingestion-runs/{run_id}`
- List and inspect ingestion runs. List supports optional `status`, optional `q` (case-insensitive substring on `original_filename` or `title`), `limit` (default 50, max 200), `offset` (default 0), `sort_by` (`started_at` | `completed_at` | `status` | `document_label`; default `started_at`), and `sort_dir` (`asc` | `desc`; default `desc`). Returns a paginated envelope: `{ runs, total_runs, total_pages, limit, offset }`

`GET /admin/source-documents`
- List source documents for admin catalog views (ingest dropdowns, video upload table, knowledge catalog). Optional `status` (`uploaded` | `ingesting` | `ingested` | `failed` | `retired`; omit for all non-retired statuses; repeat and/or comma-separate for multiple; use `status=retired` to list retired only), optional `sync_published_visible` (`true` = knowledge docs, `false` = ingest docs; omit for both), optional `source_type` (`pdf` | `pptx` | `docx` | `audio` | `video`; repeat and/or comma-separate for multiple), optional `q` (case-insensitive substring on `original_filename` or `title`), optional `uploaded_by` (hierarchy user id(s); repeat and/or comma-separate), optional `assigned` (`true` = has at least one document assignment; `false` = unassigned; omit for both); supports `limit` (default 50, max 200), `offset` (default 0), `sort_by` (`ingested_at` | `title` | `source_type` | `status` | `content_domain` | `original_filename`; default `ingested_at`), and `sort_dir` (`asc` | `desc`; default `desc`). Returns a paginated envelope: `{ source_documents, total_source_documents, total_pages, limit, offset }`. Each row includes `stored_path` (object-storage path for download via existing presign), plus `description` and `thumbnail_storage_path` when set.

`PATCH /admin/source-documents/{source_document_id}`
- Update `title` and/or `description` without re-ingest. Title, when provided, must be non-empty.

`PUT /admin/source-documents/{source_document_id}/thumbnail`
- Replace the source document thumbnail (multipart image: PNG, JPEG, or WebP). Does not re-upload the source file or start ingestion.

`POST /admin/assignments`
- Assign published modules to PO/SK users via `user_ids` and/or `upazila` names. Each stored row is one assignee. PO `user_ids` assign only that PO unless `expand_po_assignees` is true (then the PO and their direct Shastiya Kormi children). Upazila inputs expand to PO/SK users in that upazila (Area Managers excluded).

`GET /admin/assignments/{module_id}/users`
- List PO/SK users with a direct module assignment row for the given module. Returns `{ module_id, users }` where each user is a hierarchy `UserResponse` (name, role, district, upazilas).

`PUT /admin/assignments/{module_id}/users`
- Replace the full assignee set for a module via `user_ids` and/or `upazila` names (same PO expand / upazila rules as create, including optional `expand_po_assignees`). Adds missing rows, removes rows no longer in the resolved set, and preserves existing rows for unchanged assignees. Empty or omitted `user_ids` and `upazilas` clears all assignees. Returns `{ added_count, removed_count, assignment_ids }`.

`POST /admin/document-assignments`
- Assign any uploaded source document to PO/SK users via `source_document_id` plus `user_ids` and/or `upazila` names. Uses the same PO expand / upazila rules as module assignment (including optional `expand_po_assignees`). No status or `source_type` checks. Returns `{ assigned_count, assignment_ids }`. Document sync for assigned docs is not yet wired.

`GET /admin/document-assignments/{source_document_id}/users`
- List PO/SK users with a direct document assignment row for the given source document. Returns `{ source_document_id, users }` where each user is a hierarchy `UserResponse`.

`PUT /admin/document-assignments/{source_document_id}/users`
- Replace the full assignee set for a source document via `user_ids` and/or `upazila` names (same PO expand / upazila rules as create, including optional `expand_po_assignees`). Adds missing rows, removes rows no longer in the resolved set, and preserves existing rows for unchanged assignees. Empty or omitted `user_ids` and `upazilas` clears all assignees. Returns `{ added_count, removed_count, assignment_ids }`.


#### Dashboard-facing

`GET /dashboard/digital-help-modules`

`GET /dashboard/digital-help-modules/{module_id}/questions`

`GET /dashboard/digital-help-modules/{module_id}/requests`

`GET /dashboard/module-creation-suggestions`

`GET /dashboard/module-creation-suggestions/{suggestion_id}`

`GET /dashboard/team-activity`

`GET /dashboard/team-activity/users/{user_id}/questions`

`GET /dashboard/published-module-completions`

`GET /dashboard/document-usage`

Current state:
- these routes are part of the canonical API surface
- Digital-help and module-creation-suggestion reads are hierarchy-scoped: `AREA_MANAGER` sees descendant POs and their SKs (not self); `PO` sees child SKs (not self); `SHASTIYA_KORMI` sees self only; platform admins and auth-off remain unrestricted. Null `chw_id` / null evidence `sample_chw_id` are excluded for scoped viewers. Document-usage keeps include-self semantics separately.
- `GET /dashboard/digital-help-modules` ranks modules by combined `digital_help_used` + `module_requested` event volume over required `from_date`/`to_date` (UTC inclusive), keyed on concrete `module_id` (events without `module_id` ignored, including free-text requests; no family roll-up). Each item exposes `digital_help_count` and `module_requested_count`; response totals are `total_digital_help` and `total_module_requested`. Enriched with module titles from PostgreSQL; supports `limit` (default 20) and `offset` (default 0) pagination with `total_modules` in the response; `from_date > to_date` → 422
- `GET /dashboard/digital-help-modules/{module_id}/questions` uses the same auth/tenant model as the list (`get_selected_tenant_id` / authenticate `userDetail.country.tenantId`). Required `from_date`/`to_date`, `limit`/`offset` (default 50 / max 200). Returns deduplicated chatbot questions for that concrete `module_id` from `digital_help_used` (`payload_json.question`, fallback `query`): newest-first by latest occurrence, with `occurrence_count` and latest raw `question` text; blank question text omitted; `title` enriched from PostgreSQL when present (null if unknown). Empty window / unknown module → 200 with empty `questions`
- `GET /dashboard/digital-help-modules/{module_id}/requests` uses the same auth/tenant model. Required `from_date`/`to_date`. Returns a single aggregate `module_requested_count` for that concrete `module_id` only (free-text / `requested_module_name`-only events without `module_id` are not counted); includes `title` when present. No pagination
- `GET /dashboard/module-creation-suggestions` lists daily LLM suggestions for modules to create next, inferred from unattributed `digital_help_used` (no `module_id`) and free-text `module_requested` events. Required `from_date`/`to_date`, optional `limit`/`offset` (default 20). Same dashboard tenant auth and hierarchy visibility: a suggestion appears only if it has evidence whose `sample_chw_id` is in-scope; `question_count` / `request_count` / `evidence_count` are recomputed from in-scope evidence while tenant-wide `rank` is preserved. Items may be `matched_draft` (existing draft `module_id`) or `proposed_topic`. Populated by Celery beat `platform.refresh_module_creation_suggestions` (prior UTC day; still tenant-wide precompute)
- `GET /dashboard/module-creation-suggestions/{suggestion_id}` returns one suggestion with its evidence: deduped chat `questions` and free-text `requests`, filtered to in-scope `sample_chw_id` for hierarchy viewers. Wrong tenant / unknown id / no in-scope evidence → 404
- `GET /dashboard/team-activity` is hierarchy-aware under the `dashboard` prefix. Query: `from_date`, `to_date` (UTC inclusive), `limit`, `offset`, optional `user_id` (no `po_user_id`), optional `depth` (default `0`, max `2`). Returns one level at a time as flat `members[]` (each with `role` and `can_drill_down`), sorted by name. **Default focus (`depth=0`):** platform Admin / auth-off → all tenant `AREA_MANAGER`s; Area Manager → direct child POs; PO device → direct child SKs. **Skip-level (`depth`):** relative to the effective focus (caller default or `user_id`) — Admin `depth=1` → all POs under those AMs (orphan POs excluded); Admin `depth=2` → all SKs under those AMs' POs; AM `depth=1` → all SKs under that AM. Illegal `depth` for the focus role (e.g. AM `depth=2`, PO `depth≥1`) → 422. **Drill:** `?user_id=<descendant>` focuses on that user (must be in the caller's subtree, else 403) and composes with `depth` (e.g. Admin + `user_id=<AM>` + `depth=1` → SKs under that AM); AM focus → POs at `depth=0`; PO focus → SKs at `depth=0`; SK focus → empty `members` with `summary`/`total_users` for that single SK (`depth>0` → 422). AM/PO row metrics roll up from descendant SKs. `focus_user_id` echoes the query when set, otherwise null. `limit`/`offset`/`total_pages` page current-level `members` (`total_members`); `summary.*` and `total_users` count SKs under the effective focus (orphan SKs with no PO under an AM tree excluded). Returns assigned module completion, chatbot usage by module, and per-member `refreshers_generated` / `refreshers_completed`. ClickHouse reads use MVs `chw_daily_summary` and `chw_digital_help_daily` for activity/chatbot metrics; refresher counts are folded in-app from ordered `coaching_events` rows with `event_type = module_quiz_attempted` in the date window (incorrect opens a refresher per `quiz_id`, subsequent correct closes it; window-only pairing). Per-member `last_chat_at` and `last_active_at` are all-time latest activity dates (UTC midnight) from those MVs.
- `GET /dashboard/team-activity/users/{user_id}/questions` is hierarchy-aware like the list route (no `po_user_id`). Same caller gate via `resolve_team_activity_scope`: PO → own subtree; Area Manager → descendants; Admin / auth-off → unrestricted within the tenant org map. Required `from_date`/`to_date`, `limit`/`offset` (default 50 / max 200). Returns deduplicated chatbot questions for one visible member from `digital_help_used` (`payload_json.question`, fallback `query`): newest-first by latest occurrence, with `occurrence_count` and latest raw `question` text. Path `user_id` must be the caller or a descendant (unrestricted: any org-map user); unknown / out-of-subtree → 403. Blank question text is omitted.
- `GET /dashboard/published-module-completions` is Admin / Area Manager only (device principals including organizer POs → 403 via `resolve_published_module_completions_scope`; auth-off → unrestricted). Required `from_date`/`to_date` (UTC inclusive; `from_date > to_date` → 422), `limit`/`offset` (default 20 / max 200). Lists currently `lifecycle_status=published` non-FAQ modules whose `published_at` falls in the window, newest-first. Each item includes `module_id`, `module_family_id`, `title`, `published_at`, `completed_sk_count` (distinct descendant SKs with `chw_module_completion.completed_at` in the same window for that family), and `total_descendant_sk_count` (all SKs under Admin tenant tree / AM subtree via `sks_under_focus`; same on every row; also on the envelope). Completions are family-grained: multiple published versions of the same family in range share `completed_sk_count`. Zero-completion modules are included. Postgres only (no ClickHouse).
- `GET /dashboard/document-usage` aggregates `document_viewed` telemetry via the `document_view_daily` MV and raw `coaching_events` into one response (KPIs, per-document rows, event drill-down). Tenant from authenticate `userDetail.country.tenantId` via `get_selected_tenant_id` (no query `tenant_id`). Shared filters: `from`/`to`, `upazila_id`, `district`, optional `user_id` (hierarchy focus like team-activity: out-of-subtree → 403; PO → that PO + child SKs; AM → AM + descendants; SK → that user), `document_id`. Geography filters resolve via the org user map (`upazila_id` parity with `district`). Viewer scope is the authenticated principal (PO/AM include-self; platform admins / auth-off unrestricted). The MV is defined in `infra/clickhouse/init.sql` (drop legacy `document_open_daily` if present on existing envs).

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
2. Platform resolves `response_language` (or deployment primary locale). Greeting / chit-chat / crisis-looking messages may take an early `coaching_chat_route` path and return without retrieval
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
- SPICE auth middleware with admin/device authorization planes (when `SPICE_AUTH_ENABLED=true`)
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
