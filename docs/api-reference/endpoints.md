# Route index

Canonical HTTP routes for platform-api and ai-runtime. Paths below are relative to `API_ROOT_PATH` (default `/medtronics-api`). Example: `GET /medtronics-api/ready`. Auth, grants, and Problem Details: [Authentication and errors](authentication-and-errors.md), [Roles and access](../concepts/roles-and-access.md).

## Device

| Method | Path | Purpose | Details |
|---|---|---|---|
| `POST` | `/coaching/rag-query` | Cloud coaching chat | [Coaching](coaching.md) |
| `POST` | `/coaching/local-rag-query` | EDGE mode card RAG | [Coaching](coaching.md) |
| `POST` | `/telemetry/events` | Telemetry batch | [Telemetry](telemetry.md) |
| `GET` | `/sync/modules` | Published modules delta (`since`) | [Sync](sync.md) |
| `GET` | `/sync/card-embeddings` | Card local embeddings delta | [Sync](sync.md) |
| `GET` | `/sync/triggers` | Trigger definitions delta | [Sync](sync.md) |
| `GET` | `/sync/gaps` | Gaps and CHW gap state | [Sync](sync.md) |
| `GET` | `/sync/chat-faqs` | FAQ suggestion chips | [Sync](sync.md) |
| `GET` | `/sync/config` | Config and locales | [Sync](sync.md) |
| `GET` | `/sync/source-documents` | Document URLs and assignments | [Sync](sync.md) |
| `GET` | `/sync/badges` | Available and earned badges | [Sync](sync.md) |
| `POST` | `/sync/presigned-urls` | Batch presigned GET URLs | [Sync](sync.md) |
| `GET` | `/sync/video-progress` | Video watch progress delta | [Sync](sync.md) |
| `GET` | `/morning/cards` | Morning review module ids | [Morning](morning.md) |

## Admin ingest and knowledge

| Method | Path | Purpose | Details |
|---|---|---|---|
| `POST` | `/admin/ingest/upload` | Upload ingest source files | [Admin ingest](admin-ingest.md) |
| `POST` | `/admin/ingest` | Queue ingest batch | [Admin ingest](admin-ingest.md) |
| `GET` | `/admin/ingest/batches/{batch_id}` | Poll ingest batch | [Admin ingest](admin-ingest.md) |
| `POST` | `/admin/ingest/batches/{batch_id}/retry` | Retry failed stages | [Admin ingest](admin-ingest.md) |
| `POST` | `/admin/ingest/modules/{module_id}/override-merge` | Dual-path override | [Admin ingest](admin-ingest.md) |
| `POST` | `/admin/ingest/modules/{module_id}/split-merge` | Dual-path split | [Admin ingest](admin-ingest.md) |
| `GET` | `/admin/ingestion-runs` | List ingestion runs | [Admin ingest](admin-ingest.md) |
| `GET` | `/admin/ingestion-runs/{run_id}` | Ingestion run detail | [Admin ingest](admin-ingest.md) |
| `GET` | `/admin/source-documents` | List source documents | [Admin ingest](admin-ingest.md) |
| `PATCH` | `/admin/source-documents/{source_document_id}` | Update title/description | [Admin ingest](admin-ingest.md) |
| `PUT` | `/admin/source-documents/{source_document_id}/thumbnail` | Replace thumbnail | [Admin ingest](admin-ingest.md) |
| `POST` | `/admin/knowledge/upload` | Upload knowledge PDF | [Admin ingest](admin-ingest.md) |
| `GET` | `/admin/knowledge/uploaders` | Knowledge uploaders | [Admin ingest](admin-ingest.md) |
| `DELETE` | `/admin/knowledge/{source_document_id}` | Retire knowledge document | [Admin ingest](admin-ingest.md) |

## Admin modules, files, badges, hierarchy, assignments

| Method | Path | Purpose | Details |
|---|---|---|---|
| `POST` | `/admin/files` | Upload editor attachment | [Admin modules](admin-modules.md) |
| `GET` | `/admin/files/presigned-url` | Presign attachment | [Admin modules](admin-modules.md) |
| `POST` | `/admin/modules` | Create module | [Admin modules](admin-modules.md) |
| `GET` | `/admin/modules` | List modules | [Admin modules](admin-modules.md) |
| `GET` | `/admin/modules/domains` | Domain dropdown | [Admin modules](admin-modules.md) |
| `GET` | `/admin/modules/{module_id}` | Module detail | [Admin modules](admin-modules.md) |
| `PUT` | `/admin/modules/{module_id}` | Save content version | [Admin modules](admin-modules.md) |
| `DELETE` | `/admin/modules/{module_id}` | Retire module | [Admin modules](admin-modules.md) |
| `POST` | `/admin/modules/{module_id}/publish` | Publish | [Admin modules](admin-modules.md) |
| `POST` | `/admin/modules/{module_id}/deactivate` | Deactivate | [Admin modules](admin-modules.md) |
| `POST` | `/admin/modules/{module_id}/reactivate` | Reactivate | [Admin modules](admin-modules.md) |
| `POST` | `/admin/badges` | Create badge | [Admin modules](admin-modules.md) |
| `GET` | `/admin/badges` | List badges | [Admin modules](admin-modules.md) |
| `GET` | `/admin/badges/{badge_id}` | Badge detail | [Admin modules](admin-modules.md) |
| `PUT` | `/admin/badges/{badge_id}` | Update badge | [Admin modules](admin-modules.md) |
| `DELETE` | `/admin/badges/{badge_id}` | Delete badge | [Admin modules](admin-modules.md) |
| `POST` | `/admin/divisions` | Create division | [Hierarchy](hierarchy.md) |
| `GET` | `/admin/divisions` | List divisions | [Hierarchy](hierarchy.md) |
| `POST` | `/admin/districts` | Create district | [Hierarchy](hierarchy.md) |
| `GET` | `/admin/districts` | List districts | [Hierarchy](hierarchy.md) |
| `POST` | `/admin/hierarchy/users` | Create hierarchy user | [Hierarchy](hierarchy.md) |
| `GET` | `/admin/hierarchy/users` | List hierarchy users | [Hierarchy](hierarchy.md) |
| `POST` | `/admin/hierarchy/import` | Import hierarchy | [Hierarchy](hierarchy.md) |
| `GET` | `/admin/hierarchy/users/{user_id}` | User detail | [Hierarchy](hierarchy.md) |
| `PUT` | `/admin/hierarchy/users/{user_id}` | Update user | [Hierarchy](hierarchy.md) |
| `DELETE` | `/admin/hierarchy/users/{user_id}` | Delete user | [Hierarchy](hierarchy.md) |
| `POST` | `/admin/assignments` | Assign modules | [Assignments](assignments.md) |
| `GET` | `/admin/assignments/{module_id}/users` | Module assignees | [Assignments](assignments.md) |
| `PUT` | `/admin/assignments/{module_id}/users` | Replace assignees | [Assignments](assignments.md) |
| `POST` | `/admin/document-assignments` | Assign documents | [Assignments](assignments.md) |
| `GET` | `/admin/document-assignments/{source_document_id}/users` | Document assignees | [Assignments](assignments.md) |
| `PUT` | `/admin/document-assignments/{source_document_id}/users` | Replace document assignees | [Assignments](assignments.md) |
| `GET` | `/admin/configs` | List configs | [Admin modules](admin-modules.md) |
| `GET` | `/admin/configs/{key}` | Config value | [Admin modules](admin-modules.md) |
| `PUT` | `/admin/configs/{key}` | Set config | [Admin modules](admin-modules.md) |
| `GET` | `/admin/configs/{key}/changes` | Config history | [Admin modules](admin-modules.md) |
| `GET` | `/admin/prompts` | List prompts | [Admin modules](admin-modules.md) |

## Dashboard

| Method | Path | Purpose | Details |
|---|---|---|---|
| `GET` | `/dashboard/digital-help-modules` | Ranked digital-help demand | [Dashboard](dashboard.md) |
| `GET` | `/dashboard/digital-help-modules/{module_id}/questions` | Questions for a module | [Dashboard](dashboard.md) |
| `GET` | `/dashboard/digital-help-modules/{module_id}/requests` | Training requests for a module | [Dashboard](dashboard.md) |
| `GET` | `/dashboard/module-creation-suggestions` | Unattributed suggestions | [Dashboard](dashboard.md) |
| `GET` | `/dashboard/module-creation-suggestions/{suggestion_id}` | Suggestion detail | [Dashboard](dashboard.md) |
| `GET` | `/dashboard/module-demand-summary` | Assign / Publish / Create buckets | [Dashboard](dashboard.md) |
| `GET` | `/dashboard/team-activity` | Team activity | [Dashboard](dashboard.md) |
| `GET` | `/dashboard/team-activity/users/{user_id}/questions` | Member questions | [Dashboard](dashboard.md) |
| `GET` | `/dashboard/published-module-completions` | Published module completions | [Dashboard](dashboard.md) |
| `GET` | `/dashboard/document-usage` | Knowledge document usage | [Dashboard](dashboard.md) |

## Operational and auth

| Method | Path | Purpose | Details |
|---|---|---|---|
| `GET` | `/ready` | Readiness probe | [Authentication and errors](authentication-and-errors.md) |
| `POST` | `/auth/session` | Admin web session proxy | [Authentication and errors](authentication-and-errors.md) |

## AI runtime (internal)

Devices must not call these routes.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/internal/generate/{generation_type}` | Generation |
| `POST` | `/internal/embed` | Embeddings |
| `POST` | `/internal/transcribe` | Transcription |
| `GET` | `/health` | ai-runtime health |

## Next step

[Authentication and errors](authentication-and-errors.md)
