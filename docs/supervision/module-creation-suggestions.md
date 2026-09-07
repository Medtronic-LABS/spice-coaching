# Module-creation suggestions

Platform proposes modules to create next from **unattributed** chatbot questions and free-text training requests. Unattributed means the event has no `module_id` (unlike [Digital-help demand](digital-help-demand.md), which ranks attributed volume).

Route details: [Dashboard](../api-reference/dashboard.md).

**Before you start:** A scheduled job refreshes the suggestion list. Empty results mean there is not enough unattributed demand in the lookback window.

## List suggestions

Call `GET /dashboard/module-creation-suggestions`.

**Result:** Daily LLM suggestions. Digital-help and suggestion reads are hierarchy-scoped.

## Read one suggestion

Call `GET /dashboard/module-creation-suggestions/{suggestion_id}`.

## Create vs assign

1. Use [Digital-help demand](digital-help-demand.md) when the question already maps to a published `module_id` (Assign or Publish).
2. Use this page when demand has no module id (Create).
3. After you decide to create content, follow [Upload and ingest sources](../content-administration/ingest-sources.md), then publish and assign.

## Next step

[Upload and ingest sources](../content-administration/ingest-sources.md)
