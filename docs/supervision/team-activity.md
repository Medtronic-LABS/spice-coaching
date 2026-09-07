# Team activity

A [Program Organizer](../GLOSSARY.md#program-organizer) and an [Area Manager](../GLOSSARY.md#area-manager) monitor assignments, completion, and chatbot use in a date window.

Route details: [Dashboard](../api-reference/dashboard.md).

**Before you start:** Send required `from_date` and `to_date`. Assigned modules are live assignment rows whose `assigned_at` falls in the window. FAQ-only modules are excluded. Activity counts come from [Send telemetry](../device-coaching/send-telemetry.md).

## Read the team

Call `GET /dashboard/team-activity`.

**Result:** Each member row includes role, activity flags, and `performance_status` (`on_track` or `at_risk`). See [performance status](../GLOSSARY.md#performance-status) for the 60% responsive rule.

Area Manager and Program Organizer rows include a descendant summary and `can_drill_down=true`. CHW rows do not drill down.

## Drill into questions

Call `GET /dashboard/team-activity/users/{user_id}/questions` for one visible member.

## Published-module completions

Call `GET /dashboard/published-module-completions`. This route is for admin and Area Manager only.

**Result:** Currently published non-FAQ modules whose `published_at` falls in the window.

## Document usage

Call `GET /dashboard/document-usage` for knowledge-document view KPIs from `document_viewed` telemetry.

Dashboard routes return delivery and activity counts.

## Next step

[Module-creation suggestions](module-creation-suggestions.md)
