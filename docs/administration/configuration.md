# Configuration

Set these environment variables for platform and ai-runtime. Copy `.env.example` to `.env` for local development. See [Local development setup](../getting-started/local-development.md).

## Database and queues

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Async Postgres connection string |
| `DATABASE_PASSWORD` | Database password. Staging and production must not use the local default. |
| `REDIS_URL` | Redis for Celery and dedup |

## AI runtime (platform → ai-runtime)

| Variable | Purpose |
|---|---|
| `AI_RUNTIME_BASE_URL` | Internal ai-runtime URL |
| `AI_RUNTIME_TOKEN` | Shared `X-Internal-Token`. Staging and production must not use the local default. |
| `AI_RUNTIME_TIMEOUT_SECONDS` | Default LLM call timeout |
| `AI_RUNTIME_TRANSCRIBE_TIMEOUT_SECONDS` | Transcription timeout |

ai-runtime uses `INTERNAL_TOKEN` for the same shared secret.

## Inference providers (ai-runtime only)

| Variable | Purpose |
|---|---|
| `AI_CLOUD_PROVIDER` | Cloud provider |
| `GOOGLE_USE_VERTEX` | Use Vertex ADC versus API key |
| `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` | Vertex project and region |
| `GOOGLE_APPLICATION_CREDENTIALS` | Service-account path inside the container |
| `GOOGLE_API_KEY` / `GEMINI_API_KEY` | Developer API fallback when Vertex is off |
| `GOOGLE_EMBEDDING_MODEL` | Cloud embedding model |
| `LOCAL_EMBEDDING_MODEL` / `LOCAL_EMBEDDING_DEVICE` | Local embedding |
| `HUGGINGFACE_TOKEN` | Token for gated model download |
| `LOCAL_GENERATION_GGUF_PATH` or `LOCAL_GENERATION_GGUF_REPO` + `LOCAL_GENERATION_GGUF_FILE` | Local GGUF generation |
| `LOCAL_PRELOAD_ON_STARTUP` | Warm local models at startup |

## Retrieval

| Variable | Purpose |
|---|---|
| `EMBEDDING_DIMENSION` | Vector dimension (768) |
| `TOP_K` | Retrieval top-k |
| `VECTOR_STORE_BACKEND` | Vector backend (`pgvector`) |
| `COACHING_RAG_MODULE_LIMIT` | Cloud RAG module cap |
| `COACHING_LOCAL_RAG_CARD_LIMIT` | EDGE card cap |
| `RETRIEVAL_REQUIRE_VALIDATED` | Safety gate for validated content |

## SPICE auth

| Variable | Purpose |
|---|---|
| `SPICE_AUTH_ENABLED` | Toggle token validation. Must be `true` in staging and production. |
| `SPICE_AUTH_BASE_URL` | Auth-service root URL. No trailing slash. |
| `SPICE_AUTH_TIMEOUT_SECONDS` | Auth call timeout |
| `SPICE_AUTH_DEFAULT_CLIENT` | Default `client` header |
| `SPICE_AUTH_EXEMPT_PATHS` | Comma-separated unauthenticated paths |

## Object storage

| Variable | Purpose |
|---|---|
| `OBJECT_STORAGE_BACKEND` | `minio` or `s3` |
| `OBJECT_STORAGE_ENDPOINT` | S3 API endpoint |
| `OBJECT_STORAGE_PRESIGNED_ENDPOINT` | Host used in signed URLs |
| `OBJECT_STORAGE_PRESIGN_MODE` | `proxy` or `direct` |
| `OBJECT_STORAGE_ACCESS_KEY` / `OBJECT_STORAGE_SECRET_KEY` | Credentials. Staging and production must not use local MinIO defaults. |
| `OBJECT_STORAGE_BUCKET_NAME` | Bucket name |
| `ADMIN_FILE_UPLOAD_PREFIX` | Prefix for editor uploads |

## ClickHouse, locale, logging

| Variable | Purpose |
|---|---|
| `CLICKHOUSE_HOST` / `CLICKHOUSE_PORT` | Analytics store |
| `CLICKHOUSE_DATABASE` / `CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD` | Analytics credentials |
| `DEPLOYMENT_PRIMARY_LOCALE` | CHW-facing locale. Default `bn`. |
| `DEPLOYMENT_REGION_CONTEXT` | Geographic context for LLM prompts |
| `DEPLOYMENT_ADDITIONAL_LOCALES` | Extra RAG answer locales |
| `LOG_LEVEL` / `LOG_JSON` | Structured logging |
| `APP_ENV` | `development` / `staging` / `production` |

`CORS_ALLOW_ORIGINS` must not include `*` when `APP_ENV` is staging or production.

## Staging and production hardening

Set `APP_ENV=staging` or `APP_ENV=production` on shared hosts. The service fails at startup if insecure defaults remain. Set `APP_ENV=development` only on a trusted local machine.

### Platform (`platform-api` / `platform-celery-worker`)

| Variable | Requirement |
|---|---|
| `APP_ENV` | `staging` or `production` |
| `DATABASE_PASSWORD` | Non-empty. Must not be `postgres`. |
| `AI_RUNTIME_TOKEN` | Must not be the local development default. |
| `OBJECT_STORAGE_ACCESS_KEY` / `OBJECT_STORAGE_SECRET_KEY` | Must not be local MinIO defaults when set. Empty keys are allowed only with `OBJECT_STORAGE_BACKEND=s3`. |
| `SPICE_AUTH_ENABLED` | Must be `true`. |
| `CORS_ALLOW_ORIGINS` | Must not include `*`. |

### AI runtime

| Variable | Requirement |
|---|---|
| `APP_ENV` | `staging` or `production` |
| `INTERNAL_TOKEN` | Must not be the local development default. |
| `GOOGLE_API_KEY` or Vertex credentials | Required when `AI_PROVIDER=google` without Vertex. |

## Next step

[Multi-tenancy](multi-tenancy.md)
