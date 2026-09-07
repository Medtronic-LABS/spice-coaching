# Architecture

MicroCoaching sits between mobile CHW clients and cloud AI infrastructure. The Android SDK and admin web clients call platform-api. platform-api stores product state and delegates raw LLM calls to ai-runtime.

```mermaid
graph LR
    subgraph clients [Clients]
        AndroidSDK([Android SDK])
        AdminWeb([Admin Web])
        AnalyticsUI([Analytics Dashboard])
    end

    subgraph microCoaching [MicroCoaching]
        Platform[["platform-api and workers"]]
        AIRuntime[["ai-runtime"]]
    end

    subgraph external [External services]
        SPICE[SPICE Auth Service]
        Vertex[Google Vertex AI]
        MinIO[(MinIO or S3)]
    end

    subgraph dataTier [Data tier]
        PG[(PostgreSQL)]
        Redis[(Redis)]
        CH[(ClickHouse)]
    end

    AndroidSDK -->|HTTPS REST| Platform
    AdminWeb -->|HTTPS REST| Platform
    AnalyticsUI -->|HTTPS REST| Platform
    Platform -->|POST /authenticate| SPICE
    Platform -->|REST internal| AIRuntime
    Platform --> PG
    Platform --> Redis
    Platform --> CH
    Platform --> MinIO
    AIRuntime --> Vertex
```

## External dependencies

| System | Used by | Purpose | Connection |
|---|---|---|---|
| SPICE auth-service | platform-api | JWT validation | `POST {SPICE_AUTH_BASE_URL}/authenticate` |
| Google Vertex AI / Gemini | ai-runtime | Inference, vision, transcription, embeddings | SDK via ADC or API key |
| MinIO / S3 | platform-api, workers | Source documents, thumbnails, admin files | S3-compatible API |
| Analytics dashboard | Browser | Program-manager analytics UI | Calls platform dashboard routes |

## Users and clients

| Actor | Calls | Purpose |
|---|---|---|
| CHW Android SDK | `/coaching`, `/sync`, `/telemetry`, `/morning` | Offline sync, coaching RAG, telemetry, morning cards |
| Admin / reviewer web | `/admin/*` | Ingest, modules, assignments, pipeline runs |
| [Program Organizer](../GLOSSARY.md#program-organizer) / [Area Manager](../GLOSSARY.md#area-manager) | `/dashboard/*` | Dashboard analytics |
| platform-celery-worker | Redis broker | Background ingest and telemetry jobs |
| platform-api | ai-runtime internal API | Generation, embedding, transcription |

## Technology stack

See `pyproject.toml` and `uv.lock` for locked library versions.

| Category | Technology | Purpose |
|---|---|---|
| Language | Python | All services and packages |
| Package manager | uv | Workspace lock and multi-package sync |
| Web framework | FastAPI | HTTP APIs for platform-api and ai-runtime |
| ORM | SQLAlchemy async | PostgreSQL access in platform |
| Migrations | Alembic | Schema changes. Run as a separate step. |
| Vector search | Module embedding store | Module embeddings for RAG. Default adapter is pgvector. |
| Primary DB | PostgreSQL | System of record |
| Analytics DB | ClickHouse | Telemetry events and dashboard views |
| Queue broker | Redis | Celery broker and rate-limit state |
| Task queue | Celery | Ingest, post-publish, telemetry drain |
| Object storage | MinIO or AWS S3 | PDFs, thumbnails, ingest artifacts |
| AI providers | google-genai in ai-runtime only | LLM inference and embeddings |
| Auth | SPICE middleware | Authentication. DB role to route for authorization. |
| Observability | python-json-logger, request IDs | Structured logs and correlation |
| CI | GitHub Actions | Lint, security scan, typecheck, tests |
| Containers | Docker Compose | Local full stack |

Service images use `python:3.12-slim`. Healthchecks use a Python `urllib` probe. The image has no `curl`.

## Container architecture

```mermaid
graph TD
    subgraph clients2 [Clients]
        SDK[Android SDK]
        Admin[Admin Web]
    end

    subgraph appTier [Application]
        API["platform-api :8000"]
        Worker["platform-celery-worker"]
        Beat["platform-celery-beat"]
        AI["ai-runtime :8001"]
    end

    subgraph data2 [Data]
        PG2[("PostgreSQL")]
        Redis2[("Redis")]
        CH2[("ClickHouse")]
        MinIO2[("MinIO")]
    end

    SDK --> API
    Admin --> API
    API --> PG2
    API --> Redis2
    API --> CH2
    API --> MinIO2
    API -->|REST plus token| AI
    Worker --> Redis2
    Worker --> PG2
    Worker --> MinIO2
    Worker -->|REST plus token| AI
    Beat --> Redis2
    Beat --> Worker
    Worker --> CH2
```

| Unit | Purpose |
|---|---|
| platform-api | Public HTTP API on port 8000 under `/medtronics-api` (`API_ROOT_PATH`). Owns product writes and orchestration. |
| platform-celery-worker | Ingest pipeline, post-publish jobs, telemetry processing, thumbnail generation, telemetry buffer drain. No HTTP. |
| platform-celery-beat | Scheduled jobs for telemetry drain, chat FAQ aggregation, feedback summaries, and module-creation suggestion refresh. |
| ai-runtime | Stateless generation, embedding, and transcription on port 8001. Depends on AI provider credentials only. |
| migrate | Runs `alembic upgrade head` once, then exits. |

Compose host ports: [Deployable units](../administration/deployable-units.md). Directories: [Where to change code](where-to-change-code.md).

## Platform internals

Platform uses a layered pattern: FastAPI routers, domain services, repositories, SQLAlchemy models. Auth, rate limiting, and dependency injection sit in middleware. All AI calls go through `AIRuntimeClient`.

```mermaid
graph LR
    subgraph platformApi [platform-api]
        MW["Middleware"]
        API["API routers"]
        SVC["Domain services"]
        REPO["Repositories"]
        INT["Integrations"]
        WORK["Celery producers"]
    end

    HTTP["Incoming HTTP"] --> MW --> API
    API --> SVC
    SVC --> REPO --> PG[("PostgreSQL")]
    SVC --> INT
    INT --> AI["ai-runtime"]
    INT --> CH[("ClickHouse")]
    INT --> MinIO[("MinIO")]
    API --> WORK --> Redis[("Redis")]
```

Route groups live under `API_ROOT_PATH`. See [Route index](../api-reference/endpoints.md).

## ai-runtime internals

ai-runtime is thin. It validates an internal token, routes to a provider adapter, and returns a structured response. It does not persist product state. Devices do not call these routes.

| Endpoint | Purpose |
|---|---|
| `POST /internal/generate/{generation_type}` | Unified generation. The generation type selects the prompt and parser. |
| `POST /internal/embed` | Text embeddings |
| `POST /internal/transcribe` | Media transcription |
| `GET /health` | Liveness |

## RAG eval harness

`eval` is a CLI library. It is not a deployable service. See [RAG evaluation](rag-evaluation.md).

## Next step

[Data and workflows](data-and-workflows.md)
