# Dashboard

Dashboard analytics over telemetry for a [Program Organizer](../GLOSSARY.md#program-organizer) and an [Area Manager](../GLOSSARY.md#area-manager).

**How to use:** [Supervision](../supervision/README.md) — digital-help demand, team activity, and module-creation suggestions.

**Auth required:** Yes when SPICE auth is on. Hierarchy role `AREA_MANAGER`, `PO`, or `SHASTIYA_KORMI` (self only). Super Admin is unrestricted.

All routes accept optional `division_id`, `district_id`, and `upazila_id`. Repeat or comma-separate ids for OR within a dimension. AND across dimensions. Empty intersection returns `200` with empty or zero metrics.

Digital-help and suggestion reads are hierarchy-scoped:

- `AREA_MANAGER` sees descendant Program Organizers and their CHWs, not self.
- `PO` sees child CHWs, not self.
- `SHASTIYA_KORMI` sees self only.
- Platform Super Admin and auth-off remain unrestricted.

Date-range filters and ordering use UTC. ClickHouse-backed timestamps such as `last_asked_at` use device-local `timestamp_local`.

## GET /dashboard/digital-help-modules

Ranks modules by combined `digital_help_used` plus `module_requested` volume.

**Request**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `from_date` | date | Yes | Inclusive start |
| `to_date` | date | Yes | Inclusive end |
| `limit` / `offset` | int | No | Pagination |

**Response `200`:** `total_digital_help`, `total_module_requested`, `total_modules`, and `modules[]` with counts and locale-keyed `title`.

## GET /dashboard/digital-help-modules/{module_id}/questions

Deduplicated chatbot questions for that `module_id`.

## GET /dashboard/digital-help-modules/{module_id}/requests

Paginated `module_requested` events for that `module_id`.

## GET /dashboard/module-creation-suggestions

Daily LLM suggestions from unattributed questions. Detail: `GET /dashboard/module-creation-suggestions/{suggestion_id}`.

## GET /dashboard/module-demand-summary

Required `from_date` / `to_date`. Buckets: Assign, Publish, Create.

## GET /dashboard/team-activity

Required `from_date` / `to_date`. `performance_status` uses the 60% responsive rule for CHWs and roll-up for Program Organizer and Area Manager. See [performance status](../GLOSSARY.md#performance-status).

`GET /dashboard/team-activity/users/{user_id}/questions` returns questions for one visible member.

## GET /dashboard/published-module-completions

Admin / Area Manager only. Currently published non-FAQ modules whose `published_at` falls in the window.

## GET /dashboard/document-usage

Aggregates `document_viewed` telemetry into KPIs, per-document rows, and event drill-down.

**Errors**

| Status | Meaning |
|---|---|
| `401` | Missing or invalid token |
| `403` | Missing grant |
| `422` | Invalid date range or query |
| `503` | `analytics_unavailable` |

## Next step

[Route index](endpoints.md)
