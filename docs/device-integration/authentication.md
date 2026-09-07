# Authentication

When `SPICE_AUTH_ENABLED=true`, platform-api validates every request except paths in `SPICE_AUTH_EXEMPT_PATHS`. The default exempt path is `ready`.

**Before you start:** Set `SPICE_AUTH_BASE_URL` to the auth-service root as seen by platform. Do not add a trailing slash.

## How a request is authenticated

1. The client sends `Authorization: Bearer <jwt>`.
2. The client sends `client` (`mob` or `web`). Default is `SPICE_AUTH_DEFAULT_CLIENT`.
3. Web clients can also send `auth-cookie`.
4. Platform calls SPICE `POST {SPICE_AUTH_BASE_URL}/authenticate`.
5. Non-super principals must bind to a hierarchy user row.
6. Platform checks the hierarchy role against the route catalogue.

**Result:** The request continues with a selected tenant and a role grant check. Upstream authenticate failures surface as `401` `not_authenticated`.

`POST /auth/session` proxies session authentication to SPICE and forwards response cookies.

Local Compose keeps `SPICE_AUTH_ENABLED=false`.

## Identity planes

| Plane | What it is |
|---|---|
| Hierarchy role | `AREA_MANAGER`, `PO`, `SHASTIYA_KORMI`, `SUPER_ADMIN` on the `users` row |
| SPICE principal | `SUPER_USER` / `JOB_USER` bypass grants; `isSuperUser` / `isJobUser` can mint a root Super Admin row once |

Grant table and client headers: [Roles and access](../concepts/roles-and-access.md).

## Tenant selection

When auth is on, tenant comes from `userDetail.country.tenantId`. Missing country tenant returns `401` `not_authenticated`. See [Multi-tenancy](../administration/multi-tenancy.md).

## Next step

[PII boundary](pii-boundary.md)
