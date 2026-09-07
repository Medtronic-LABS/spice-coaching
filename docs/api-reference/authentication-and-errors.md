# Authentication and errors

Auth procedure for integrators: [Authentication](../device-integration/authentication.md). Grant table: [Roles and access](../concepts/roles-and-access.md).

## Auth required

Yes, when `SPICE_AUTH_ENABLED=true`. The default exempt path is `ready`.

Send:

| Header | Required | Description |
|---|---|---|
| `Authorization` | Yes | `Bearer <jwt>` |
| `client` | No | `mob` for the SDK, `web` for admin. Default is `SPICE_AUTH_DEFAULT_CLIENT`. |
| `auth-cookie` | No | Web session cookie |

Upstream authenticate failures return `401` `not_authenticated`. Missing grants return `403`.

## POST /auth/session

Proxies SPICE session login for admin web.

**Auth required:** SPICE auth-service. This route is not a device route.

## GET /ready

Readiness probe for PostgreSQL, Redis, ClickHouse, ai-runtime, and object storage.

**Auth required:** No, when `ready` is in `SPICE_AUTH_EXEMPT_PATHS`.

## Error responses

Every HTTP error from platform-api and ai-runtime returns `Content-Type: application/problem+json`.

| Field | Type | Description |
|---|---|---|
| `type` | string | Relative catalogue pointer `docs/error-codes.json#{code}` |
| `title` | string | Short title from the code |
| `status` | int | HTTP status |
| `detail` | string | Technical message. Not user-facing copy. |
| `instance` | string | Request path |
| `code` | string | Stable machine code. Clients map this to UX strings. |

Validation failures (`422`) include `errors[]`.

**Example RFC 7807 Problem Details response:**

```json
{
  "type": "docs/error-codes.json#not_authenticated",
  "title": "Not Authenticated",
  "status": 401,
  "detail": "Bearer token is missing or expired in upstream auth-service",
  "instance": "/medtronics-api/coaching/rag-query",
  "code": "not_authenticated"
}
```

**Example validation failure (`422`):**

```json
{
  "type": "docs/error-codes.json#validation_error",
  "title": "Validation Error",
  "status": 422,
  "detail": "Request body validation failed",
  "instance": "/medtronics-api/telemetry/events",
  "code": "validation_error",
  "errors": [
    {
      "loc": ["body", "events", 0, "event_family"],
      "msg": "Input should be 'learning', 'coaching', 'clinical_observed', 'digital' or 'system'",
      "type": "enum"
    }
  ]
}
```

Do not move `docs/error-codes.json`. See [Error catalogue](../appendix/error-catalogue.md).

## Next step

[Route index](endpoints.md)
