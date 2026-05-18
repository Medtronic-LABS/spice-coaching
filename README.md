# MicroCoaching Backend

MicroCoaching is implemented as a stateful platform service plus a private AI runtime inside one monorepo.

This document is the canonical reference for:
- the backend architecture
- the public and internal endpoint contract
- the current implementation status

Old drifted route names are not part of the contract and should not be used.

## Quick Start Docs

- Docs index and reading order: `docs/README.md`
- Setup issues and fixes: `docs/SETUP_TROUBLESHOOTING.md`
- Codebase map and ownership: `docs/PROJECT_NAVIGATION.md`

## Architecture

### Deployables

`platform-api`
- Public API for the Android SDK, admin flows, telemetry ingest, sync, and dashboards
- Owns PostgreSQL writes, ClickHouse writes, orchestration, and final response validation

`platform-worker`
- Async worker process from the same `platform_service` codebase
- Owns ingestion jobs, quiz jobs, and queued gap-profile updates

`ai-runtime`
- Private internal inference service
- Owns model-provider execution, embedding generation, and runtime response parsing
- Does not own PostgreSQL, ClickHouse, or public product workflows

### Shared Packages

`packages/contracts`
- Pydantic contracts, enums, DTOs

`packages/foundation`
- Shared config, logging, tracing, and lightweight infra helpers

### Ownership Rules

Platform owns:
- PostgreSQL schema and repositories
- Alembic migrations
- telemetry ingest and analytics writes
- sync contracts
- final coaching-card validation
- admin and dashboard APIs

AI runtime owns:
- provider adapters
- raw generation execution
- embedding generation
- runtime parsing

Shared packages do not own:
- SQLAlchemy models
- repositories
- business workflows
- domain services

## Repo Layout

```text
coaching-platform/
├── pyproject.toml
├── README.md
├── docker-compose.yml
├── infra/
│   ├── alembic/
│   └── alembic.ini
├── packages/
│   ├── contracts/
│   └── foundation/
└── services/
    ├── platform/
    │   └── src/platform_service/
    └── ai-runtime/
        └── src/ai_runtime/
```

## Canonical Endpoint Contract

### Platform API

#### Device-facing

`POST /coaching/counselling`
- Primary counselling flow
- Platform retrieves scenarios, builds prompt context, calls `ai-runtime`, validates output, and returns the final card

`POST /coaching/quiz-answer`
- Records quiz answer correctness
- Updates gap state directly for this synchronous product flow

`POST /coaching/it-help`
- Returns SPICE product/tooling help text via `ai-runtime`

`POST /telemetry/events`
- Accepts telemetry batches from the SDK
- Writes analytics rows to ClickHouse
- Queues quiz-related gap updates to Redis for background processing

`GET /scenarios/sync?since_version=N`
- Returns validated scenarios and quizzes newer than the supplied version

`GET /config/sync`
- Returns current config thresholds for device sync

`GET /morning/cards?chw_id=<int>`
- Returns prioritized scenario IDs for morning review
- Uses the configured `morning_cards_max` threshold

#### Admin-facing

`POST /admin/documents/upload`
- Uploads a SOP PDF and enqueues ingestion

`GET /admin/documents/{document_id}`
- Returns document status

`GET /admin/scenarios`
- Lists scenarios with optional filters

`GET /admin/scenarios/{scenario_id}`
- Returns scenario detail

`POST /admin/scenarios/{scenario_id}/validate`
- Marks a scenario validated

`POST /admin/scenarios/{scenario_id}/quiz/generate`
- Enqueues quiz generation for a scenario

`GET /admin/quiz-jobs/{job_id}`
- Polls quiz generation job status

#### Dashboard-facing

`GET /dashboard/supervisor/{chw_id}`

`GET /dashboard/district/{upazila_id}`

`GET /dashboard/llm-quality`

Current state:
- these routes are part of the canonical API surface
- `GET /dashboard/supervisor/{chw_id}` reads from the ClickHouse `chw_daily_summary` materialized view (see `infra/clickhouse/init.sql`)
- `GET /dashboard/llm-quality` queries ClickHouse when `llm_daily_summary` exists in the deployment
- `GET /dashboard/district/{upazila_id}` still returns `501 Not Implemented` until implemented

#### Operational

`GET /health`
- Basic liveness endpoint

### AI Runtime

#### Internal-only

`POST /internal/generate/{generation_type}`
- Canonical private generation endpoint
- Supported generation types are validated against the shared enum
- This intentionally consolidates counselling, IT help, extraction, and quiz generation into one internal route

`POST /internal/embed`
- Private embedding endpoint used by platform ingestion/retrieval flows

`GET /health`
- Basic runtime liveness endpoint

## Request Flows

### Counselling

1. SDK calls `POST /coaching/counselling`
2. Platform embeds the request context
3. Platform retrieves the best matching scenario
4. Platform loads glossary rules and prompt templates
5. Platform calls `POST /internal/generate/{generation_type}` on `ai-runtime`
6. Platform validates and sanitizes the returned card
7. Platform returns the final `CoachingCardResponse`

### Telemetry

1. SDK calls `POST /telemetry/events`
2. Platform validates and translates telemetry rows
3. Platform writes accepted telemetry to ClickHouse
4. Platform queues quiz-related gap updates to Redis
5. Worker consumes queued gap-profile jobs and updates PostgreSQL state

### Sync

1. SDK calls `GET /scenarios/sync`
2. Platform returns validated scenarios and quizzes since the requested version
3. SDK calls `GET /config/sync`
4. Platform returns current threshold/config values for device behavior

## Current Implementation Status

### Implemented

- monorepo layout with `platform`, `ai-runtime`, `contracts`, and `foundation`
- single Alembic chain under `infra/alembic`
- scenario sync and config sync
- counselling orchestration via platform to internal AI runtime
- telemetry ingest with ClickHouse writes
- Redis-backed worker processing for:
  - document ingestion
  - quiz generation
  - queued gap-profile updates
- morning-card selection with config-driven `morning_cards_max`
- canonical public route names aligned to the current plan

### Intentionally Designed This Way

- `ai-runtime` uses one generic internal generation route:
  - `POST /internal/generate/{generation_type}`
- This is an intentional consolidation, not route drift

### Not Yet Fully Implemented

- dashboard analytics queries behind `/dashboard/*`
- admin auth / role enforcement
- readiness-grade health checks
- full config-management admin endpoints
- richer dashboard and analytics materialization flows

## Standards Decisions

- No public generic chatbot or unrestricted RAG endpoints are exposed
- The SDK talks only to `platform-api`
- `ai-runtime` is private and token-protected
- Platform is the system of record
- Legacy drifted route aliases are not part of the API contract
- The workspace is managed with `uv`, and `uv.lock` should be committed

## Local Development

### Prerequisites (first-run)

```bash
cp .env.example .env
uv sync --locked --all-packages --group dev
```

Then edit `.env`:

- The preferred Google auth path is **Vertex AI service account**.
  Set `GOOGLE_USE_VERTEX=true`, `GOOGLE_CLOUD_PROJECT`,
  `GOOGLE_CLOUD_LOCATION`, and point `GCP_SERVICE_ACCOUNT_JSON_HOST_PATH`
  at your service-account JSON on the host. `GOOGLE_API_KEY` is then
  ignored.
- As a fallback (Developer API key auth) set `GOOGLE_USE_VERTEX=false`
  and put a key in `GOOGLE_API_KEY` (or `GEMINI_API_KEY`).

If `GOOGLE_USE_VERTEX=true` and `GCP_SERVICE_ACCOUNT_JSON_HOST_PATH` is
not set, `docker compose` fails at parse time — by design. See
`docs/SETUP_TROUBLESHOOTING.md` for other known failures.

### Environment

### Run services

Platform API:

```bash
uv run uvicorn platform_service.main:app --host 0.0.0.0 --port 8000
```

Platform worker:

```bash
uv run python -m platform_service.workers.main
```

AI runtime:

```bash
uv run uvicorn ai_runtime.main:app --host 0.0.0.0 --port 8001
```

### Run with Docker Compose

1. Create a root `.env` file (or export variables in your shell) and set:
   - Either Vertex creds (`GOOGLE_USE_VERTEX=true` plus
     `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and
     `GCP_SERVICE_ACCOUNT_JSON_HOST_PATH`) **or** an API key
     (`GOOGLE_API_KEY` / `GEMINI_API_KEY`) — see `.env.example`
   - `AI_RUNTIME_TOKEN` (defaults to `dev-internal-token`; the services
     refuse to start in `APP_ENV=production` while this default is in
     use)
   - `APP_ENV` (optional, defaults to `development`)
2. Start the stack:

```bash
docker compose up --build
```

Expected compose behavior:
- `migrate` runs once and exits with code `0`
- `clickhouse-init` runs once and exits with code `0`
- `db`, `redis`, `clickhouse`, `ai-runtime`, and `platform-api` are running
- `platform-celery-worker` and `platform-celery-beat` are running

Quick verification:

```bash
docker compose ps
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/ready
curl -fsS http://localhost:8001/health
```

### Migrations

Run Alembic as a separate step:

```bash
uv run alembic -c infra/alembic.ini upgrade head
```

Migrations should not be auto-run by application startup.

## Next Recommended Work

1. Implement dashboard queries behind the canonical `/dashboard/*` routes.
2. Add authentication and authorization for admin and internal operational endpoints.
3. Add readiness endpoints that verify PostgreSQL and Redis.
4. Add remaining planned admin config-management flows.
5. Add real automated tests for platform, ai-runtime, and integration flows.

## Production deployment warning

The shipped `docker-compose.yml` is for **local development only**:

- Default credentials (`postgres` / `postgres`, `dev-internal-token`)
  are committed. Replace `AI_RUNTIME_TOKEN`, `POSTGRES_PASSWORD`, and
  any other secret-shaped env var before running anywhere reachable
  from a network you don't control. The platform and ai-runtime
  services refuse to start when `APP_ENV=production` while
  `AI_RUNTIME_TOKEN` is still the dev default.
- The base compose file does **not** publish Postgres, Redis, or
  ClickHouse ports to the host. The local-dev override
  (`docker-compose.override.yml`, gitignored) republishes them on
  `localhost`. Do not run that override on a public host.
- Admin endpoints under `/admin/*` ship unauthenticated. Put them
  behind a reverse proxy with auth before any non-development use.
- The Alembic chain no longer auto-loads
  `seed/platform_models_module_data.sql`. Load seed data manually only
  after confirming you have redistribution rights — see
  `seed/README.md`.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for development setup, test,
lint, and PR conventions.

## Security

Please report security issues privately — see
[`SECURITY.md`](SECURITY.md). Do not open public issues for suspected
vulnerabilities.

## License

This project is licensed under the Apache License, Version 2.0. See
[`LICENSE`](LICENSE) for the full text.
