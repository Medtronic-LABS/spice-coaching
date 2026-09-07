# Send telemetry

The SDK sends raw [telemetry](../GLOSSARY.md#telemetry) observations. The backend writes analytics and updates operational state. Personal identifiers must not appear on any event.

Route details: [Telemetry](../api-reference/telemetry.md).

**Before you start:** Hash SPICE `patientId` to `patient_id_hash` before the value enters the SDK. Keep a stable event `id` UUID across retries. The backend deduplicates on `id` with Redis SET-NX (24 hour TTL). ClickHouse is for analytics. PostgreSQL is operational truth.

## Post a batch

Maximum 500 events per batch.

1. Build a `TelemetryBatch` with `sdk_version`, `chw_id`, optional `tenant_id`, and `events`.
2. Do not put `sdk_version`, `chw_id`, or `tenant_id` on individual events.
3. Call `POST /telemetry/events`.

**Result:** The ACK lists event ids in `accepted`, `rejected`, `duplicates`, and `buffered`. Treat `buffered` as ingested. The drain job retries the analytics write.

Unknown `event_family` returns `422`. Unknown `event_type` values land in ClickHouse only.

## When to send which event

| Situation | `event_family` | `event_type` | Notes |
|---|---|---|---|
| Module shown in Morning review | `coaching` | `module_delivered` | Include module ids when known |
| Card opened | `coaching` | `module_card_viewed` | Awards learning points |
| Quiz finished | `coaching` | `module_quiz_attempted` | Requires `quiz_score_pct`. Set `outcome` |
| CHW requests training | `coaching` | `module_requested` | Creates assignment when `module_id` is published |
| Video watch progress | `coaching` | `video_progress_updated` | Requires progress keys in `payload_json` |
| Knowledge document opened | `coaching` | `document_viewed` | Requires `payload_json.source_document_id` |
| SPICE workflow action | `coaching` | `spice_action_observed` | Discriminate with `payload_json.kind`. Leave `outcome` null |
| Chat / digital help | `digital` | `digital_help_used` | Include `payload_json.question`. See [Ask the coaching chatbot](coaching-chat.md) |

## What the backend does

| Event type | Extra effect |
|---|---|
| `module_requested` | Creates a per-user assignment when `module_id` is a published module |
| `video_progress_updated` | Upserts watch progress |
| `module_delivered`, `module_card_viewed`, `module_quiz_attempted` | Updates completion and learning points |
| `spice_action_observed` | Updates learning points and gap observation state |
| `document_viewed` | Counts knowledge-document views. No learning points |
| `digital_help_used` | Feeds FAQ mining |

Invalid modules and duplicate training requests are no-ops inside the worker. The ACK still lists the event as accepted.

Celery jobs are not gated on ClickHouse insert success. ClickHouse insert failure buffers rows to a Redis retry queue.

## Request training

Send `event_type=module_requested` with top-level `module_id` or `payload_json.requested_module_name`, or both. Optional `payload_json.reason`. Accepted requests appear on the next `GET /sync/modules` under `requested_modules`. See [Assign modules and documents](../content-administration/assign-content.md) for how admins grant modules.

## Payload keys for selected types

`video_progress_updated` requires `payload_json` keys `source_document_id`, `last_position_ms`, and `percent_watched` (0–100). The worker monotonically upserts watch progress.

`document_viewed` requires `payload_json.source_document_id`. Mint a new event `id` per view.

`spice_action_observed` uses `event_family: "coaching"`. Put workflow specifics in `payload_json.kind`. Leave `outcome` null.

`module_quiz_attempted` uses per-question attempts (`quiz_id`). `outcome` still affects gap state and learning points.

## Next step

[Badges and learning points](badges-and-learning.md)

## See also

* [Morning review](morning-review.md) — suggestions fed by gap and quiz telemetry
* [Digital-help demand](../supervision/digital-help-demand.md) — dashboard ranking of `digital_help_used` and `module_requested`
