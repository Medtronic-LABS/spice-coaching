# Roles and access

For a particular request, identity comes from [SPICE](../GLOSSARY.md#spice). Authorization binds a SPICE principal to a hierarchy user in the selected [tenant](../GLOSSARY.md#tenant).

The grant table below is the source for path-template access by hierarchy role. Other pages link here.

## Hierarchy roles

| Role | Default grants |
|---|---|
| `AREA_MANAGER` ([Area Manager](../GLOSSARY.md#area-manager)) | All `/admin/*` and `/dashboard/*` path templates |
| `PO` ([Program Organizer](../GLOSSARY.md#program-organizer)) | All `/dashboard/*` plus device routes |
| `SHASTIYA_KORMI` ([CHW](../GLOSSARY.md#chw)) | Device routes only |
| `SUPER_ADMIN` ([Super Admin](../GLOSSARY.md#super-admin)) | All catalogued path templates except `/sync/*` |

Device routes are `/telemetry`, `/sync`, `/morning`, and `/coaching`. We can also set specific authorization by updating the routes within the datastore for the role and route mapping.

Path templates are exact FastAPI paths relative to `API_ROOT_PATH`. Grants are method-agnostic. Missing catalogue entries and missing grants return `403`.

## SPICE principals

SPICE `SUPER_USER` and `JOB_USER` bypass route-grant checks.

When the principal is SPICE `isSuperUser`, `isJobUser`, or has token role `SUPER_ADMIN` and no hierarchy row yet, platform inserts a root Super Admin row and continues. Existing rows are never updated.

## Dashboard visibility

- Area Manager sees descendant Program Organizers and their CHWs, not self.
- Program Organizer sees child CHWs, not self.
- CHW sees self only.
- Super Admin and auth-off remain unrestricted.

## Clients

| Client | `client` header | Routes |
|---|---|---|
| Android SDK | `mob` | Device routes |
| Admin web | `web` | `/admin/*`, `/dashboard/*`, `POST /auth/session` |

## Next step

[Authentication](../device-integration/authentication.md)
