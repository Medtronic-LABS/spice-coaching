# Multi-Tenancy Model

MicroCoaching is deployed as a **multi-tenant** platform. Platform `tenant_id`
values are **`BIGINT NOT NULL`**, aligned with SPICE integer tenant IDs
(organization ids).

## Data model

- Parent/root tables carry a required `tenant_id` (`BIGINT`). There is **no**
  shared/global row via `NULL` — every tenant-scoped row belongs to exactly one
  tenant.
- Child and junction tables (for example `module_card`, `source_page`,
  `ingestion_run`, `badge_module`) do **not** denormalize `tenant_id`; they
  inherit tenancy through their parent.
- Repository queries use `tenant_scope_filter()` from
  [`tenant_scope.py`](../services/platform/src/platform_service/db/tenant_scope.py),
  which is exact equality on `tenant_id`.
- Unresolved create paths default to `DEFAULT_TENANT_ID = 0`
  ([`default_tenant.py`](../services/platform/src/platform_service/db/default_tenant.py)).
  Historical rows stamped as `tenant_id=1` under the previous default are left
  as-is (no backfill).

## Request plane (country-scoped)

Selected tenant is resolved once per request in
[`SpiceAuthMiddleware`](../services/platform/src/platform_service/auth/spice_auth_middleware.py):

1. Call auth-service `/authenticate` and read
   **`userDetail.country.tenantId`** (coaching is always country-scoped).
2. Top-level `userDetail.tenantId`, request header **`TenantId`**, and
   body/query `tenant_id` are **ignored** for selection (header may still be
   sent by clients for compatibility).
3. When SPICE auth is enabled (and the path is not exempt), missing
   `country` / `country.tenantId` → `not_authenticated` (401). There is no
   `organizationIds` membership check for the selected country tenant.
4. When auth is disabled or the path is exempt (e.g. `/ready`), selected
   tenant is **`0`**.

Helpers:

- `get_selected_tenant_id(request)` —
  [`spice_user.py`](../services/platform/src/platform_service/auth/spice_user.py)
- Plane resolvers in
  [`spice_identity.py`](../services/platform/src/platform_service/auth/spice_identity.py)
  return that same int (body/query `tenant_id` does **not** select the tenant).

The former `SPICE_TENANT_ID_MAP` UUID bridge has been removed. Platform
`tenant_id` **is** the SPICE country tenant id from authenticate.

## Planes

| Plane | Tenant resolution | Scope |
|-------|-------------------|--------|
| Device (`/sync`, `/coaching`, `/morning`, `/telemetry`) | `get_selected_tenant_id` / `resolve_tenant_id_for_device_route` | `userDetail.country.tenantId` via middleware |
| Dashboard (`/dashboard/*`) | `get_selected_tenant_id` | Same |
| Admin (`/admin/*`) | `get_selected_tenant_id` | Same; creates/lists stamp and filter by selected tenant |

Outbound calls to ai-runtime forward `TenantId` (the country tenant value)
for logging/context only; ai-runtime remains datastore-stateless.

## Workers

Celery workers bind the selected-tenant ContextVar (via
`using_selected_tenant`) so outbound AI headers and `llm_call_cache` keys
match the data being processed:

| Worker class | Tenant source |
|--------------|---------------|
| Request-triggered telemetry (module completion, training request, video progress) | `tenant_id` stamped into the Celery payload from `get_selected_tenant_id` at enqueue |
| Ingest / thumbnail / pipeline / post-publish | `source_document.tenant_id` or `module.tenant_id` loaded at job start |
| Periodic Beat (chat FAQ, feedback summary, module-creation suggestions) | Each discovered tenant in the fan-out loop |

When AUTH is on (`selected tenant != 0`), `POST /admin/ingest` rejects
source documents whose `tenant_id` does not match the authenticate-selected
tenant (client sees `source_not_found`). When AUTH is off (tenant `0`), that
ownership check is skipped for local/dev convenience.

Stage D module families inherit `tenant_id` from their source document(s);
conflicting tenants across a single create fail loudly.

## Parent/child org hierarchy

Selected tenant is the country tenant from authenticate — not derived from
`organizationIds`. Parent→child org expansion (spice `OrganizationUtil`) for
downstream data scoping is deferred.

District / hierarchy-user tables (`district`, `users`) are tenant-scoped
parent tables (`tenant_id BIGINT NOT NULL`). They model Area Manager →
PO (Program Organizer) → Shastiya Kormi under a district for import and SPICE
id/role binding. Subtree data-access scoping for dashboard/sync is not
yet wired through these tables.
