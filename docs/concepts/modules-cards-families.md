# Modules, cards, and families

A [module](../GLOSSARY.md#module) is one coaching topic. [Cards](../GLOSSARY.md#card) are screens inside that module. A [module family](../GLOSSARY.md#module-family) is the stable identity across content versions.

## Units

1. Cards belong to exactly one module row. Cross-module card reuse is not a concept.
2. Each card has `card_family_id` plus `card_version`. Telemetry uses `card_family_id`.
3. Each saved content change creates a new module row in the same family. `module.version` increases.
4. `PUT /admin/modules/{id}` requires `expected_version`. A stale write returns `409` `module_version_conflict`.

A complete content snapshot that matches the latest module row in the family is a no-op. The response then reuses the existing `id` and `version`.

Cards are relational rows. `module.module_json` holds module-level data such as attachments.

## Lifecycle

| Status | Meaning |
|---|---|
| `draft` | Editable. Not on device sync. |
| `review_pending` | [Dual-path merge](../GLOSSARY.md#dual-path-merge) pair. Needs override or split. |
| `published` | Eligible for device sync when assigned. |
| `deactivated` | Hidden from training. Still listed in default All. |
| `retired` | Soft-deleted. Default list omits it. |

`DELETE /admin/modules/{id}` sets `lifecycle_status=retired`.

When ingest finds a similar published module, it writes a dual-path pair. See [Review dual-path merges](../content-administration/review-merges.md).

Admins assign published modules through `/admin/assignments`. See [Assign modules and documents](../content-administration/assign-content.md). Quality flags on cards are warnings for reviewers; they do not block publish. Sync exposes them so the SDK can render them.

## Next step

[Edit and publish modules](../content-administration/edit-and-publish.md)
