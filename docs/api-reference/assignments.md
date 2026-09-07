# Assignments

Assign published modules and source documents to users or geography.

**Auth required:** Yes when SPICE auth is on. Hierarchy role `AREA_MANAGER` or `SUPER_ADMIN`.

## POST /admin/assignments

**Request**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `module_id` | UUID | Yes | Published module |
| `user_ids` | int[] | No | Hierarchy user ids |
| `upazila_ids` | int[] | No | Expand to users in those upazilas |
| `district_ids` | int[] | No | Expand to users in those districts |
| `division_ids` | int[] | No | Expand to users in those divisions |
| `expand_po_assignees` | bool | No | Default false |

Send at least one assignee dimension.

**Response `201`:** Assignment created.

## GET /admin/assignments/{module_id}/users

**Response `200`**

| Field | Type | Description |
|---|---|---|
| `module_id` | UUID | Module |
| `users` | array | `id`, `name`, `role`, geography refs |

## PUT /admin/assignments/{module_id}/users

Replace the assignee set. Same expand fields as create.

**Response `200`**

| Field | Type | Description |
|---|---|---|
| `added_count` | int | Newly assigned |
| `removed_count` | int | Removed |
| `assignment_ids` | string[] | Resulting assignment ids |

## POST /admin/document-assignments

Same expand rules with `source_document_id` instead of `module_id`.

`GET` and `PUT /admin/document-assignments/{source_document_id}/users` list or replace document assignees.

**Errors**

| Status | Meaning |
|---|---|
| `401` | Missing or invalid token |
| `403` | Missing grant |
| `404` | Module or document not found |
| `422` | `assignment_validation_error` |

## Next step

[Hierarchy](hierarchy.md)
