# Telemetry

## POST /telemetry/events

Accepts telemetry batches from the SDK. Writes analytics rows. Queues completion, training-request, and video-progress jobs.

**Auth required:** Yes when SPICE auth is on. Hierarchy role `SHASTIYA_KORMI` or `PO`.

**Request**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `sdk_version` | string | Yes | Free-form. Stored for triage. |
| `chw_id` | integer | Yes | SPICE CHW identifier |
| `tenant_id` | integer or null | No | Optional |
| `events` | array | Yes | Max 500 `TelemetryEvent` objects |

Do not put `sdk_version`, `chw_id`, or `tenant_id` on individual events.

### Event identity

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | SDK-generated UUID. Stable across retries. |
| `event_schema_version` | int | No | Default `1` |
| `session_id` | string or null | No | Free-form session identifier |
| `event_date` | date `YYYY-MM-DD` | Yes | Local-calendar date |
| `timestamp_local` | int | Yes | Local epoch seconds |
| `timestamp_utc` | int or null | No | UTC epoch seconds. Backend derives it if absent. |

### Classification

Allowed `event_family` values: `learning`, `coaching`, `clinical_observed`, `digital`, `system`. Unknown family returns `422`. Unknown `event_type` values land in ClickHouse only.

| Field | Type | Required | Description |
|---|---|---|---|
| `event_family` | enum | Yes | Family |
| `event_type` | enum or string | Yes | Type |

### Module and quiz identifiers

| Field | Type | Description |
|---|---|---|
| `module_family_id` | UUID or null | Stable across module content versions |
| `module_id` | UUID or null | Specific module row |
| `module_version` | int or null | Content version on the family |
| `card_family_id` | UUID or null | From the sync bundle card payload |
| `quiz_id` | UUID or null | `module_quiz_question.id` on `module_quiz_attempted` |
| `quiz_score_pct` | float 0.0–1.0 or null | Required on `module_quiz_attempted` |

### Patient fields

Use on events that carry clinical context. Hash SPICE `patientId` to `patient_id_hash` before the value enters the SDK.

| Field | Type | Description |
|---|---|---|
| `patient_id_hash` | string or null | SHA-256 hex of SPICE `patientId` |
| `patient_visit_id` | string or null | SPICE encounter id |
| `village_id` | string or null | SPICE generic `villageId` |
| `upazila_id` | string or null | SPICE generic `chiefdomId` |

### Other fields

| Field | Type | Description |
|---|---|---|
| `inference_mode` | enum or null | `online`, `edge`, `cached`, `unknown` |
| `payload_json` | object | Event-specific inputs. Default `{}` |
| `outcome` | enum or null | Set on quiz events. Leave null on `spice_action_observed` |
| `network_state` | string or null | Free-form |

The backend deduplicates on event `id` with Redis SET-NX (24 hour TTL). ClickHouse is for analytics. PostgreSQL is operational truth.

**Response `200`**

| Field | Type | Description |
|---|---|---|
| `accepted` | string[] | Event ids ingested |
| `rejected` | string[] | Event ids rejected |
| `duplicates` | string[] | Event ids already seen |
| `buffered` | string[] | Event ids stored for analytics retry. Treat as ingested. |
| `errors` | string[] | Rejection reasons |

**Errors**

| Status | Meaning |
|---|---|
| `401` | Missing or invalid token |
| `403` | Missing grant |
| `422` | Schema or family validation |

When to send which event: [Send telemetry](../device-coaching/send-telemetry.md).

## Next step

[Send telemetry](../device-coaching/send-telemetry.md)
