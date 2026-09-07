# Supervision

A [Program Organizer](../GLOSSARY.md#program-organizer) and an [Area Manager](../GLOSSARY.md#area-manager) monitor digital-help demand, team activity, and module-creation suggestions on the dashboard.

All dashboard routes accept optional `division_id`, `district_id`, and `upazila_id`. Repeat or comma-separate ids for OR within a dimension. AND across dimensions. Empty intersection returns `200` with empty or zero metrics.

Visibility follows the hierarchy. See [Roles and access](../concepts/roles-and-access.md).

In this section:

* [Digital-help demand](digital-help-demand.md)
* [Team activity](team-activity.md)
* [Module-creation suggestions](module-creation-suggestions.md)

## See also

* [Device coaching](../device-coaching/README.md) — chatbot and telemetry that feed these metrics
* [Dashboard](../api-reference/dashboard.md) — HTTP routes for this section
* [Content administration](../content-administration/README.md) — create and assign modules suggested here
