"""platform-api FastAPI application entrypoint.

Run as:
    uvicorn platform_service.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

# Load .env before any other import that touches Settings. Pydantic-settings
# handles declared fields, but environment variables consumed by external
# SDKs (notably GOOGLE_APPLICATION_CREDENTIALS for google-genai) are read
# directly from os.environ — this ensures they are populated.
from pathlib import Path

try:
    from dotenv import load_dotenv

    _here = Path(__file__).resolve()
    for _candidate in (_here.parents[4] / ".env", _here.parents[3] / ".env"):
        if _candidate.exists():
            load_dotenv(_candidate, override=False)
            break
except ImportError:
    pass

import logging  # noqa: E402
import sys  # noqa: E402

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mc_foundation.logging import setup_logging
from redis.asyncio import Redis
from sqlalchemy import text

from platform_service.api.admin_ingest import router as admin_ingest_router
from platform_service.api.admin_modules import router as admin_modules_router
from platform_service.api.dashboard import router as dashboard_router
from platform_service.api.morning import router as morning_router
from platform_service.api.sync import router as sync_router
from platform_service.api.telemetry import router as telemetry_router
from platform_service.clickhouse.client import ClickHouseClient
from platform_service.config import get_settings
from platform_service.db.base import SessionLocal


def _setup_logging(settings) -> None:  # type: ignore[no-untyped-def]
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_json:
        try:
            from pythonjsonlogger import jsonlogger

            handler.setFormatter(jsonlogger.JsonFormatter())
        except ImportError:
            pass
    logging.basicConfig(level=level, handlers=[handler], force=True)


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(
        service_name=settings.log_service_name or settings.app_name,
        log_level=settings.log_level,
        json_logs=settings.log_json,
        app_env=settings.app_env,
    )
    _setup_logging(settings)
    clickhouse_client = ClickHouseClient()

    fastapi_app = FastAPI(
        title="MicroCoaching Platform API",
        version="0.1.0",
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url=None,
    )

    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    fastapi_app.include_router(telemetry_router)
    fastapi_app.include_router(admin_ingest_router)
    fastapi_app.include_router(admin_modules_router)
    fastapi_app.include_router(dashboard_router)
    fastapi_app.include_router(morning_router)
    fastapi_app.include_router(sync_router)

    @fastapi_app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": settings.app_name}

    @fastapi_app.get("/ready")
    async def ready() -> dict:
        checks: dict[str, str] = {}

        try:
            async with SessionLocal() as session:
                await session.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "error"

        try:
            redis = Redis.from_url(settings.redis_url, decode_responses=True)
            try:
                await redis.ping()
            finally:
                await redis.aclose()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "error"

        try:
            await clickhouse_client.query_rows("SELECT 1")
            checks["clickhouse"] = "ok"
        except Exception:
            checks["clickhouse"] = "error"

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{settings.ai_runtime_base_url.rstrip('/')}/health")
                response.raise_for_status()
            checks["ai_runtime"] = "ok"
        except Exception:
            checks["ai_runtime"] = "error"

        if any(value != "ok" for value in checks.values()):
            raise HTTPException(status_code=503, detail={"status": "degraded", "checks": checks})

        return {"status": "ok", "service": settings.app_name, "checks": checks}

    return fastapi_app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
