"""Internal embed endpoint — platform → ai-runtime.

POST /internal/embed
Body: {"texts": ["...", "..."]}
Returns: {"embeddings": [[0.1, 0.2, ...], ...]}
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ai_runtime.config import get_settings
from ai_runtime.services.prompt_executor import PromptExecutor

router = APIRouter(prefix="/internal", tags=["internal"])
logger = logging.getLogger(__name__)

_executor = PromptExecutor()


class EmbedRequest(BaseModel):
    texts: list[str]


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]


def _verify_token(request: Request) -> None:
    settings = get_settings()
    token = request.headers.get("X-Internal-Token", "")
    if token != settings.internal_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing internal token",
        )


@router.post("/embed", response_model=EmbedResponse)
async def embed(body: EmbedRequest, request: Request) -> EmbedResponse:
    """Return embedding vectors for a list of texts."""
    _verify_token(request)
    if not body.texts:
        return EmbedResponse(embeddings=[])
    if len(body.texts) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 texts per request")
    embeddings = await _executor.embed(body.texts)
    return EmbedResponse(embeddings=embeddings)
