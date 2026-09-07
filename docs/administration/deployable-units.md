# Deployable units

MicroCoaching is one workspace with these processes.

| Unit | What it does |
|---|---|
| `platform-api` | Public HTTP API. Owns product writes, orchestration, and response validation. |
| `platform-worker` | Celery jobs. Owns ingest, post-publish, and telemetry side-effects. Compose service: `platform-celery-worker`. |
| `platform-celery-beat` | Scheduled jobs. Owns telemetry drain, chat FAQ aggregation, feedback summaries, and module-creation suggestion refresh. |
| `ai-runtime` | Model-provider calls. No PostgreSQL, Redis, ClickHouse, or public product workflows. |
| `migrate` | Runs Alembic once, then exits. |

Compose also runs Postgres with pgvector, Redis, ClickHouse, and MinIO.

Host ports in Compose:

| Process | Host port |
|---|---|
| platform-api | `18000` |
| ai-runtime | `18001` |
| Optional analytics dashboard | `18080` when you start the dashboard profile |
| Optional GitBook site (MkDocs) | `18081` when you start the `docs-static` profile |

The SDK talks only to platform-api. Devices do not call ai-runtime.

Do not run Alembic at application startup.

## Next step

[Configuration](configuration.md)
