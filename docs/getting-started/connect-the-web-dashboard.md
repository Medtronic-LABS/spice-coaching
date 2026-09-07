# Connect the web dashboard

The analytics dashboard is a separate web application (`micro-learning-analytics-dashboard`). It talks only to platform-api. It does not call ai-runtime.

**Before you start:** Run [Local development setup](local-development.md). Clone or build the sibling dashboard repo, or set `ANALYTICS_DASHBOARD_BUILD_CONTEXT` to that path. Read [Roles and access](../concepts/roles-and-access.md) for hierarchy grants on `/admin/*` and `/dashboard/*`.

## Send auth headers

On every web call, send:

1. `Authorization: Bearer <jwt>`
2. `client: web`

Platform forwards these headers to SPICE `POST /authenticate` when `SPICE_AUTH_ENABLED=true`.

When `SPICE_AUTH_ENABLED=false` (local Compose default in `.env.example`), you can call admin and dashboard routes without a JWT.

Do not send `X-Admin-File-Token`. Optional audit header: `X-Admin-Caller-Id`.

## First successful open

1. Confirm platform-api is healthy on host port `18000`.
2. Set browser-reachable build args in `.env`. Use host ports, not Docker DNS names.

```bash
ANALYTICS_DASHBOARD_BUILD_CONTEXT=../micro-learning-analytics-dashboard
VITE_ADMIN_API_BASE_URL=http://localhost:18000/medtronics-api
VITE_USE_MOCK_API=false
```

3. Start the optional dashboard profile.

```bash
docker compose --profile dashboard up --build
```

4. Open `http://localhost:18080` in a browser.

**Result:** The UI loads against local platform-api. Admin work continues in [Content administration](../content-administration/README.md). Supervision metrics continue in [Supervision](../supervision/README.md).

## Next step

[Supervision](../supervision/README.md) · [Content administration](../content-administration/README.md)
