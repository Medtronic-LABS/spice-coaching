# Edit and publish modules

Admins create, edit, publish, deactivate, and retire modules. Each saved content change creates a new module row in the same family.

**Before you start:** Use the module id returned by the last save. Do not keep using an old id after PUT. List filters and query params: [Admin modules](../api-reference/admin-modules.md).

## Create a module

Call `POST /admin/modules`. Optional `content_domain` is `clinical`, `digital`, or `operational`. Default is `clinical`.

Set `chatbot_faqs_only` true only when the module is FAQ knowledge. Those modules are excluded from CHW training and assignments.

## Save an edit

1. Call `GET /admin/modules/{module_id}` for the full snapshot.
2. Send `PUT /admin/modules/{module_id}` with the full `module_json` and `expected_version`.
3. Use `response.id` after save.

**Result:** A content change creates a new version. A complete matching snapshot reuses `id` and `version`. A stale `expected_version` returns `409` `module_version_conflict`.

The reviewer can set `visibility_window` for a “what is new” period. Routine reviewer correction and real content change both create a new content version.

## Publish, deactivate, reactivate, retire

- `POST /admin/modules/{module_id}/publish` publishes the latest module row in the family.
- `POST /admin/modules/{module_id}/deactivate` hides the module from training.
- `POST /admin/modules/{module_id}/reactivate` restores a deactivated module.
- `DELETE /admin/modules/{module_id}` sets `retired`.

Quality flags on cards do not block publish. The validator does not auto-truncate LLM output. A reviewer edits the module when a fix is needed. Sync exposes those flags so the SDK can render them.

Default All on `GET /admin/modules` hides the `review_pending` secondary of a dual-path pair. See [Review dual-path merges](review-merges.md).

## Next step

[Assign modules and documents](assign-content.md)
