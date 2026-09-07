# Digital-help demand

A [Program Organizer](../GLOSSARY.md#program-organizer) and an [Area Manager](../GLOSSARY.md#area-manager) see which modules attract chatbot questions and training requests.

Route details: [Dashboard](../api-reference/dashboard.md).

**Before you start:** Send required `from_date` and `to_date`. Digital-help reads are hierarchy-scoped. Upstream events come from [Ask the coaching chatbot](../device-coaching/coaching-chat.md) and [Send telemetry](../device-coaching/send-telemetry.md).

## Rank modules

Call `GET /dashboard/digital-help-modules`.

**Result:** Modules ranked by combined `digital_help_used` plus `module_requested` volume. Ranking uses concrete `module_id`. Events without `module_id` are ignored.

The envelope includes `total_digital_help`, `total_module_requested`, `total_modules`, `limit`, and `offset`.

## Drill into one module

1. Call `GET /dashboard/digital-help-modules/{module_id}/questions` for deduplicated chatbot questions.
2. Call `GET /dashboard/digital-help-modules/{module_id}/requests` for paginated training requests.

ClickHouse-backed timestamps such as `last_asked_at` use device-local wall clocks from telemetry `timestamp_local`. Date-range filters and result ordering remain UTC.

## Demand summary

Call `GET /dashboard/module-demand-summary` with the same date range.

**Result:** Structured JSON with buckets Assign, Publish, and Create.

## Next step

[Team activity](team-activity.md)
