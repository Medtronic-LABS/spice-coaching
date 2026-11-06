# Assign modules and documents

Admins assign published modules and source documents to hierarchy users or to geography.

**Before you start:** The module must be published. FAQ-only modules are not assignable to CHW training.

## All SKs or specific SKs

Every module and source document carries an `assign_to_all` flag. Delivery follows one rule:

```
if assign_to_all:            every SK in the tenant (including SKs added later)
elif explicit assignment row: that SK only
else:                         not assigned
```

- New uploads and newly created modules default to `assign_to_all=true`. Content that existed before the flag was introduced is `false`, so current behavior is unchanged until an admin changes it.
- Choose **all** at upload (`assign_to_all` form field on `POST /admin/ingest/upload`) or at publish (`assign_to_all` in the body of `POST /admin/modules/{module_id}/publish`, which also applies to the module's linked videos).
- Toggle later with `PUT /admin/modules/{module_id}/assign-to-all` or `PUT /admin/source-documents/{source_document_id}/assign-to-all`.
- Choose **specific** by setting the flag to `false` and using the explicit assignment calls below. Explicit assignment rows are never changed by the flag.

## Assign a module

Call `POST /admin/assignments` with `module_id` and at least one of `user_ids`, `upazila_ids`, `district_ids`, or `division_ids`.

**Result:** Assignees appear in `GET /admin/assignments/{module_id}/users`. The next `GET /sync/modules` returns those ids in `assigned_module_ids` (together with every published module that has `assign_to_all=true`).

Replace the assignee set with `PUT /admin/assignments/{module_id}/users`. The response includes `added_count` and `removed_count`.

## Assign a source document

Call `POST /admin/document-assignments` with `source_document_id` and the same expand rules.

**Result:** The next `GET /sync/source-documents` includes the document in `assigned_documents`. That snapshot ignores `since` and also contains every non-retired document with `assign_to_all=true`.

## CHW self-request

A CHW can request training through telemetry `module_requested`. Valid published `module_id` requests create a per-user assignment. Requests appear on the next sync under `requested_modules`.

## Next step

[Knowledge library](knowledge-library.md)
