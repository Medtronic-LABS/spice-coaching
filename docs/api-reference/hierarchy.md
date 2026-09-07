# Hierarchy

Tenant-scoped geography and users. Tree rule: Area Manager → Program Organizer → CHW, same district and tenant.

**Auth required:** Yes when SPICE auth is on. Hierarchy role `AREA_MANAGER` or `SUPER_ADMIN`.

Roles on create: `AREA_MANAGER` | `PO` | `SHASTIYA_KORMI`. Super Admin is not creatable here.

## Divisions

| Method | Path | Notes |
|---|---|---|
| POST | `/admin/divisions` | Body: `name`. Response `201` |
| GET | `/admin/divisions` | Paginated list |
| GET | `/admin/divisions/{division_id}` | One row |
| PUT | `/admin/divisions/{division_id}` | Body: `name` |
| DELETE | `/admin/divisions/{division_id}` | Cascades to districts. `204` |

## Districts

| Method | Path | Notes |
|---|---|---|
| POST | `/admin/districts` | Body: `name`, optional `division_id` |
| GET | `/admin/districts` | Paginated list |
| GET / PUT / DELETE | `/admin/districts/{district_id}` | DELETE cascades to users under that district |

## Upazilas

| Method | Path | Notes |
|---|---|---|
| POST | `/admin/upazilas` | Body: `name`, `district_id` |
| GET | `/admin/upazilas` | Paginated list |
| GET / PUT / DELETE | `/admin/upazilas/{upazila_id}` | Tenant-scoped |

List envelopes include `total`, `total_pages`, `limit`, and `offset`.

## Users

## POST /admin/hierarchy/users

**Request**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `id` | int | Yes | Externally supplied. Greater than 0 |
| `name` | string | Yes | Display name |
| `role` | enum | Yes | `AREA_MANAGER` \| `PO` \| `SHASTIYA_KORMI` |
| `district_id` | int | Yes | District in the selected tenant |
| `parent_id` | int | No | Parent user |
| `upazila_ids` | int[] | No | Upazila links |

**Response `201`:** User row with geography refs and `tenant_id`.

`GET /admin/hierarchy/users` lists users. `GET`, `PUT`, and `DELETE /admin/hierarchy/users/{user_id}` read, update, or cascade-delete.

## POST /admin/hierarchy/import

Multipart upload of a `.csv` or `.xlsx` org chart. One atomic transaction. Caps: 5 MiB and 20_000 data rows.

**Response `200`:** Counts under `divisions`, `districts`, `upazilas`, and `users` (`created`, `updated`, `deleted`).

**Errors**

| Status | Meaning |
|---|---|
| `404` | `hierarchy_division_not_found`, `hierarchy_district_not_found`, `hierarchy_user_not_found` |
| `409` | `hierarchy_user_conflict` |
| `422` | `hierarchy_import_invalid`, `hierarchy_parent_invalid`, `hierarchy_role_mismatch` |

## Next step

[Dashboard](dashboard.md)
