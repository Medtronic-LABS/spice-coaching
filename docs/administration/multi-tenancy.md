# Multi-tenancy

Platform `tenant_id` values are `BIGINT NOT NULL`. They match SPICE integer country tenant IDs.

Parent tables carry a required `tenant_id`. There is no shared row through `NULL`. Child and junction tables do not copy `tenant_id`. They inherit tenancy through the parent. Examples: `module_card`, `source_page`, `ingestion_run`, `badge_module`.

Unresolved create paths use `DEFAULT_TENANT_ID = 0`. Some existing rows use `tenant_id=1`. Do not backfill those rows.

## How the selected tenant is chosen

`SpiceAuthMiddleware` selects the tenant once per request.

1. Call auth-service `/authenticate`.
2. Read `userDetail.country.tenantId`. Coaching is always country-scoped.
3. Ignore top-level `userDetail.tenantId`, request header `TenantId`, and body or query `tenant_id` for selection. Clients may still send the header.
4. When SPICE auth is on and the path is not exempt, missing `country` or `country.tenantId` returns `401` `not_authenticated`.
5. When auth is off, the selected tenant is the `TenantId` header, or `0` when the header is absent or invalid.
6. Exempt paths such as `/ready` always use `0`.

## Planes

| Plane | Tenant resolution |
|---|---|
| Device (`/sync`, `/coaching`, `/morning`, `/telemetry`) | Country tenant from authenticate |
| Dashboard (`/dashboard/*`) | Same |
| Admin (`/admin/*`) | Same. Creates and lists stamp and filter by the selected tenant. |

ai-runtime stays datastore-stateless. Outbound calls forward `TenantId` for logging only.

## Workers

Celery workers bind the selected tenant for the job. Outbound AI headers and LLM cache keys then match the data in the job.

| Worker class | Tenant source |
|---|---|
| Request-triggered telemetry | `tenant_id` in the Celery payload at enqueue |
| Ingest, thumbnail, pipeline, post-publish | `source_document.tenant_id` or `module.tenant_id` at job start |
| Periodic Beat | Each discovered tenant in the fan-out loop |

When auth is on (selected tenant is not `0`), `POST /admin/ingest` rejects source documents whose `tenant_id` does not match the selected tenant. The client sees `source_not_found`. When auth is off (tenant `0`), that ownership check is skipped.

Module families from `card_draft` inherit `tenant_id` from their source document. Conflicting tenants on one create fail.

Selected tenant is the country tenant from authenticate. It is not derived from `organizationIds`.

## Next step

[Language and locales](language-and-locales.md)
