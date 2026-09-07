# Assign modules and documents

Admins assign published modules and source documents to hierarchy users or to geography.

**Before you start:** The module must be published. FAQ-only modules are not assignable to CHW training.

## Assign a module

Call `POST /admin/assignments` with `module_id` and at least one of `user_ids`, `upazila_ids`, `district_ids`, or `division_ids`.

**Result:** Assignees appear in `GET /admin/assignments/{module_id}/users`. The next `GET /sync/modules` returns those ids in `assigned_module_ids`.

Replace the assignee set with `PUT /admin/assignments/{module_id}/users`. The response includes `added_count` and `removed_count`.

## Assign a source document

Call `POST /admin/document-assignments` with `source_document_id` and the same expand rules.

**Result:** The next `GET /sync/source-documents` includes the document in `assigned_documents`. That snapshot ignores `since`.

## CHW self-request

A CHW can request training through telemetry `module_requested`. Valid published `module_id` requests create a per-user assignment. Requests appear on the next sync under `requested_modules`.

## Next step

[Knowledge library](knowledge-library.md)
