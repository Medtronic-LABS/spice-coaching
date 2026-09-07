# Local Compose failures

This page lists setup failures seen in local development and the verified fixes.

## Compose prints that `version` is obsolete

**Cause:** Docker Compose no longer needs a top-level `version` field.

**Fix:**

1. Keep the Compose file without a top-level `version` field.

**Result:** `docker compose up` does not print that warning.

## Containers stay in `health: starting` and logs show `curl: not found`

**Cause:** Service images use `python:3.12-slim`. That image has no `curl`.

**Fix:**

1. Keep healthchecks on the Python urllib probe.
2. Do not add healthchecks that need `curl`, `wget`, or `psql` unless you install those tools.

platform-api probes `/ready`. ai-runtime probes `/health`.

**Result:** `docker compose ps` shows both services `healthy`.

## Redis prints `Memory overcommit must be enabled`

**Cause:** The Linux host has `vm.overcommit_memory=0`.

**Fix:**

1. On Linux, run `sudo sysctl vm.overcommit_memory=1`.
2. To persist across reboots, add `vm.overcommit_memory = 1` to `/etc/sysctl.conf`.

Local development usually continues. Reliability can drop under memory pressure.

## Manual Alembic fails with `DATABASE_URL is not set`

**Cause:** The shell does not export `DATABASE_URL`.

**Fix:**

1. Keep `.env` at the repository root. Alembic loads it.
2. Run `uv run alembic -c infra/alembic.ini upgrade head`.

## New migration files exist, but migrate exits without applying them

**Cause:** `docker compose up` does not rebuild images.

**Fix:**

1. Run `docker compose build migrate`.
2. Run `docker compose run --rm migrate alembic -c infra/alembic.ini upgrade head`.

Treat a migration change as build then run.

## Migrate exits with `Can't locate revision identified by ...`

**Cause:** The Postgres volume was migrated with a different Alembic chain than the current image.

**Fix if you can drop local data:**

1. Run `docker compose down -v`.
2. Run `docker compose up -d`.

**Fix if you must keep data:** stamp `alembic_version` to the head revision that this image contains, then run upgrade. Confirm the head revision in `infra/alembic/versions/` first.

## Container start fails with `executable file not found in $PATH`

**Cause:** `uv sync` installs scripts into `/app/.venv/bin/`.

**Fix:**

1. Keep `ENV PATH="/app/.venv/bin:$PATH"` in service Dockerfiles after `uv sync`.
2. Keep host `.venv/` directories out of the image.
3. Rebuild: `docker compose build --no-cache platform-api ai-runtime migrate`.

Check: `curl -fsS http://localhost:18000/medtronics-api/ready`

## ai-runtime build fails with `Could not find gcc`

**Cause:** PyPI offered a source distribution. `python:3.12-slim` has no C compiler.

**Fix:**

1. Keep the uv index for prebuilt wheels in the workspace.
2. Rebuild ai-runtime with `docker compose build --no-cache ai-runtime`.

## Ingest returns `202` but poll status stays `queued`

**Cause:** Pipeline work runs on `platform-celery-worker`. The worker must reach object storage.

**Fix:**

1. Confirm `docker compose ps` shows `platform-celery-worker` up.
2. Read logs: `docker compose logs platform-celery-worker`.
3. Confirm the worker has the same object-storage settings as platform-api.

## First local embed is slow or returns `embedding_failed`

**Cause:** Local EmbeddingGemma downloads on first use, or the license and token are missing.

**Fix:**

1. Accept the EmbeddingGemma license on Hugging Face.
2. Set `HUGGINGFACE_TOKEN` for ai-runtime.
3. Give ai-runtime about 1 GB free RAM.

Local embeddings return 768-dimension vectors. Cloud embed remains the default when `use_local` is false.

## Local generation is slow or returns `generation_failed`

**Cause:** No GGUF model, or first load is still downloading.

**Fix:**

1. Set `LOCAL_GENERATION_GGUF_PATH`, or set `LOCAL_GENERATION_GGUF_REPO` and `LOCAL_GENERATION_GGUF_FILE`.
2. Set `HUGGINGFACE_TOKEN` if the GGUF repo needs auth.
3. Set `LOCAL_PRELOAD_ON_STARTUP=true` for local work.

Local generation is text-only. Image attachments are rejected when `use_local` is true.

## Presigned GET URLs fail behind nginx

**Cause:** The host in the signed URL must match the public hostname.

**Fix:**

1. Set the presigned endpoint to the public hostname.
2. Set the secure flag when the public URL uses HTTPS.
3. Use a dedicated hostname or port. Do not put MinIO under a path prefix of the platform API.

## Next step

[Local development setup](../getting-started/local-development.md)
