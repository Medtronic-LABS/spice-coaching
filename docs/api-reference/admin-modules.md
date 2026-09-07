# Admin modules

Module CRUD, files, badges, configs, and prompts.

**Auth required:** Yes when SPICE auth is on. Hierarchy role `AREA_MANAGER` or `SUPER_ADMIN`.

## POST /admin/modules

Create a module.

**Request**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `title` | locale map | Yes | Locale-keyed title |
| `description` | locale map | No | Locale-keyed description |
| `content_domain` | enum | No | `clinical` \| `digital` \| `operational`. Default `clinical` |
| `module_json` | object | No | Cards and attachments |
| `chatbot_faqs_only` | bool | No | FAQ-only modules skip CHW training. Default false |

**Response `201`:** Module detail including `id`, `module_family_id`, and `version`.

## GET /admin/modules

**Request**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `status` | enum | No | Omit for All. Retired excluded. Deactivated and review_pending included |
| `domain` | string | No | Clinical topic tag on `module.domain` (e.g. `anc`, `malaria`, `hypertension`). |
| `content_domain` | enum | No | Architectural category (`clinical`, `digital`, `operational`). Repeat or comma-separate. |
| `date_from` / `date_to` | ISO 8601 | No | Inclusive range. `422` when `date_from > date_to`. |
| `chatbot_faqs_only` | bool | No | Omit for all |
| `division_id` / `district_id` / `upazila_id` | int | No | Assignee geography |
| `limit` | int | No | Default 50. Max 200 |
| `offset` | int | No | Default 0 |
| `sort_by` | string | No | `created_at` \| `updated_at` \| `published_at` \| `activated_at` \| `deactivated_at` \| `title` \| `domain` \| `lifecycle_status` |
| `sort_dir` | string | No | Default `desc` |
| `latest_version_only` | bool | No | Default true. One row per family |

`422` when `date_from > date_to`.

**Response `200`:** `{ modules, total_modules, total_pages, limit, offset }`.

## GET /admin/modules/domains

Distinct `module.domain` values. Pass the same `status` as the active tab.

## GET /admin/modules/{module_id}

Full module detail. File attachments have `object_name` only. This call does not return play URLs.

## PUT /admin/modules/{module_id}

Requires `expected_version`. Stale version returns `409` `module_version_conflict`. A complete matching snapshot is a no-op and returns the existing `id` / `version`. Always use the returned `id`.

## POST /admin/modules/{module_id}/publish

Publishes the latest module row in the family.

## POST /admin/modules/{module_id}/deactivate

Deactivates the module. Response is lifecycle state.

## POST /admin/modules/{module_id}/reactivate

Reactivates a deactivated module.

## DELETE /admin/modules/{module_id}

Retires the module. When the module is a dual-path merge primary, the secondary is retired in the same operation.

## POST /admin/files

Upload an admin file asset. Response `201` includes `object_name`, `storage_path`, `content_type`, `size_bytes`, and `original_filename`.

`GET /admin/files/presigned-url` returns a short-lived GET URL. Query: `object_name`, optional `disposition`, optional `expires_seconds`.

## Badges

`POST /admin/badges` and `GET /admin/badges` create and list active badges. `module_ids` must only reference published modules at write time. `DELETE` soft-deletes (`status=deleted`).

## Configs and prompts

`GET /admin/configs` lists thresholds. `PUT /admin/configs/{key}` updates one key. `GET /admin/configs/{key}/changes` lists history.

`GET /admin/prompts` lists prompt templates. Related routes list versions, variables, create a version, activate a version, and preview a render.

## Next step

[Assignments](assignments.md)
