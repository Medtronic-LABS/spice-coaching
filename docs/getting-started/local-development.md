# Local development setup

Run the backend on a trusted local machine. Local Compose keeps SPICE auth off when `.env` follows `.env.example`.

**Before you start:** Install Docker Compose, `uv`, and Git. Prepare Google credentials for LLM calls (Vertex service account or a developer API key). To start the analytics UI, keep the sibling `micro-learning-analytics-dashboard` repo next to this repo or set `ANALYTICS_DASHBOARD_BUILD_CONTEXT`.

## Copy the environment file

1. Copy `.env.example` to `.env`.
2. Choose one inference path:

| Path | Required settings |
|---|---|
| Vertex (default in `.env.example`) | `GOOGLE_USE_VERTEX=true`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and `GCP_SERVICE_ACCOUNT_JSON_HOST_PATH` to a host JSON file |
| Developer API key | `GOOGLE_USE_VERTEX=false` and `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) |

3. Leave other defaults for local development.

If you skip the copy, Compose fails at parse time when a required variable is missing.

## Install workspace packages

```bash
uv sync --locked --all-packages --group dev
uv run pre-commit install
```

**Result:** The workspace packages and git hooks are installed.

## What Compose starts

| Process | Host port | Notes |
|---|---|---|
| Postgres (pgvector) | `15432` | Product database |
| Redis | `16379` | Celery and dedup |
| ClickHouse HTTP | `18123` | Analytics |
| MinIO API / console | `19902` / `19001` | Object storage |
| platform-api | `18000` | Public HTTP API (`API_ROOT_PATH` `/medtronics-api`) |
| ai-runtime | `18001` | Private model calls |
| platform-celery-worker | — | Ingest and side-effects |
| platform-celery-beat | — | Scheduled jobs |
| migrate | — | Runs once, then exits |
| clickhouse-init | — | Runs once, then exits |
| analytics-dashboard (optional) | `18080` | Profile `dashboard` |
| docs-static (optional) | `18081` | Profile `docs-static` |

See [Deployable units](../administration/deployable-units.md).

## Start the default stack

1. Confirm `.env` has valid credentials for your inference path.
2. Start the stack.

```bash
docker compose up --build
```

**Result:**

- `migrate` exits with code `0`.
- `clickhouse-init` exits with code `0`.
- `db`, `redis`, `clickhouse`, `minio`, `ai-runtime`, and `platform-api` are running.
- `platform-celery-worker` and `platform-celery-beat` are running.

## Check the probes

```bash
docker compose ps
curl -fsS http://localhost:18000/medtronics-api/ready
curl -fsS http://localhost:18001/health
```

**Result:** Both probes return OK. OpenAPI docs load at `http://localhost:18000/docs`.

## Optional: analytics dashboard

Start the UI with the `dashboard` profile after platform-api is healthy.

```bash
docker compose --profile dashboard up --build
```

Set `VITE_ADMIN_API_BASE_URL` to a browser-reachable URL such as `http://localhost:18000/medtronics-api`. Do not use Docker DNS names in `VITE_*` values.

**Result:** The UI is on `http://localhost:18080`. Full connect steps: [Connect the web dashboard](connect-the-web-dashboard.md).

## Optional: GitBook site

The default stack does not start the product book. MkDocs publishes `docs/` when you enable the `docs-static` profile.

```bash
docker compose --profile docs-static up docs-static --build
```

**Result:** nginx serves the built site at `http://localhost:18081`. Rebuild the image after you change markdown.

```bash
curl -fsS http://localhost:18081/
```

**Result:** The probe returns HTTP 200.

## Run Alembic as a separate step

Do not run migrations at application startup.

```bash
uv run alembic -c infra/alembic.ini upgrade head
```

After you pull new migration files, rebuild the migrate image, then run it.

```bash
docker compose build migrate
docker compose run --rm migrate alembic -c infra/alembic.ini upgrade head
```

## Run services on the host

Use these commands when you do not use Compose for the application processes. Compose still supplies Postgres, Redis, ClickHouse, and MinIO.

Host ports differ from Compose published ports: host uvicorn uses `8000` / `8001`; Compose maps `18000` / `18001`.

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

## Verify code quality

Run fast unit tests that do not need an external database:

```bash
uv run pytest -m "not requires_db"
```

For integration tests marked `requires_db`:

1. Start Postgres (`docker compose up -d db`).
2. Export a test URL on the Compose host port, for example:

```bash
export DATABASE_URL_TEST="postgresql+asyncpg://postgres:postgres@localhost:15432/microcoaching"
```

3. Run `uv run pytest -m "requires_db"`.

Run lint and format checks:

```bash
uv run pre-commit run --all-files
```

## Stop and reset

Stop containers and keep volumes:

```bash
docker compose down
```

Wipe local database and object volumes only when you intend to discard local data:

```bash
docker compose down -v
```

See [Configuration](../administration/configuration.md) for names and purpose, including staging and production hardening. See [Local Compose failures](../troubleshooting/README.md) if a probe fails.

## Next step

[Connect the Android SDK](connect-the-android-sdk.md) · [Connect the web dashboard](connect-the-web-dashboard.md)
