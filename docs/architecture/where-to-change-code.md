# Where to change code

## Monorepo structure

```text
spice-coaching/
├── infra/
│   ├── alembic/
│   └── alembic.ini
├── packages/
│   ├── contracts/
│   └── foundation/
├── services/
│   ├── platform/
│   └── ai-runtime/
├── eval/
└── docs/
```

## What lives where

### `services/platform`

- Public API routes (device, admin, dashboard).
- Domain workflows and orchestration.
- Redis queue producers and Celery workers.
- PostgreSQL and ClickHouse integration.

### `services/ai-runtime`

- Internal inference endpoints.
- Provider adapters and generation pipelines.
- Embedding generation and runtime parsing.

### `packages/contracts`

- Shared DTOs, enums, and API contracts.

### `packages/foundation`

- Shared config, logging, tracing, and helper utilities.

### `infra/alembic`

- Migration scripts and Alembic environment wiring.

### `eval`

- RAG eval CLI and golden datasets.

### `docs`

- This GitBook. Product behaviour and contributor contracts.

## Where to start by task

### Add or change a public endpoint

1. Start in `services/platform/src/platform_service`.
2. Update route handlers and service logic.
3. Update shared request and response contracts in `packages/contracts` if needed.
4. Update [Route index](../api-reference/endpoints.md) in the same change.
5. Verify with OpenAPI at `http://localhost:18000/docs` when Compose is running.

### Update AI generation behaviour

1. Start in `services/ai-runtime/src/ai_runtime`.
2. Change provider adapters, prompts, or generation pipelines.
3. Validate with runtime health and an internal generation request.

### Change schema or persistence

1. Add a migration in `infra/alembic/versions`.
2. Update platform models and repositories in `services/platform`.
3. Run `uv run alembic -c infra/alembic.ini upgrade head`.

### Change queues or background jobs

1. Start in `services/platform/src/platform_service/workers` and `services/platform/src/platform_service/celery_tasks.py`.
2. Keep queue names and payload contracts aligned with producers.
3. Verify worker startup logs and queue consumption.
4. See [Background tasks & workers](background-tasks.md) for the complete task and schedule catalogue.

### Update shared contracts or foundation utilities

1. Start in `packages/contracts` or `packages/foundation`.
2. Confirm platform-api and ai-runtime still run.

### Change the RAG eval harness

1. Start in `eval/src/eval/rag`.
2. See [RAG evaluation](rag-evaluation.md).

### Change documentation

1. Edit the matching page under `docs/`.
2. Keep [Route index](../api-reference/endpoints.md) aligned with route names.
3. If you add, remove, or rename `mc_contracts.errors.ErrorCode`, update `docs/error-codes.json` in the same change.

## Next step

[Local development setup](../getting-started/local-development.md)
