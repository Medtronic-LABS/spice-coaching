# Manage the org hierarchy

The org tree in a tenant is Division → District → Upazila, with Area Manager → Program Organizer → CHW.

**Before you start:** All writes stamp the selected tenant. Create requires an externally supplied integer user `id`. Roles on this API are `AREA_MANAGER`, `PO`, and `SHASTIYA_KORMI`. Super Admin is not creatable here.

## Create geography

1. Call `POST /admin/divisions` with `name`.
2. Call `POST /admin/districts` with `name` and `division_id`.
3. Call `POST /admin/upazilas` with `name` and `district_id`.

`DELETE` on a division cascades to districts. `DELETE` on a district cascades to hierarchy users under that district.

## Create a user

Call `POST /admin/hierarchy/users` with `id`, `name`, `role`, `district_id`, optional `parent_id`, and optional `upazila_ids`.

Tree rule: Area Manager → Program Organizer → CHW, same district and tenant.

`DELETE /admin/hierarchy/users/{user_id}` cascades to descendant users.

## Import a spreadsheet

Call `POST /admin/hierarchy/import` with a `.csv` or `.xlsx` file.

**Result:** One atomic transaction. Caps: 5 MiB and 20_000 data rows. Counts return under `divisions`, `districts`, `upazilas`, and `users`.

## Next step

[Roles and access](../concepts/roles-and-access.md)
