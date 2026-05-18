"""FastAPI dependency injectors for the platform service."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from platform_service.db.base import SessionLocal
from platform_service.integrations.ai_runtime_client import AIRuntimeClient

# Shared ai-runtime client instance (stateless, reuse httpx connections)
_ai_client: AIRuntimeClient | None = None


def get_ai_client() -> AIRuntimeClient:
    global _ai_client
    if _ai_client is None:
        _ai_client = AIRuntimeClient()
    return _ai_client


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
