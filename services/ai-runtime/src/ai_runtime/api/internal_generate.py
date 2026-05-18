"""Internal generate endpoints — platform → ai-runtime.

POST /internal/generate/{generation_type}

All four generation types (counselling, it_help, extraction, quiz) share the
same handler. The generation_type path param is validated against GenerationType.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from mc_contracts.enums import GenerationType
from mc_contracts.internal_ai import InferenceRequest, InferenceResponse

from ai_runtime.config import get_settings
from ai_runtime.services.prompt_executor import PromptExecutor

router = APIRouter(prefix="/internal", tags=["internal"])
logger = logging.getLogger(__name__)

_executor = PromptExecutor()


def _verify_token(request: Request) -> None:
    settings = get_settings()
    token = request.headers.get("X-Internal-Token", "")
    if token != settings.internal_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing internal token",
        )


@router.post("/generate/{generation_type}", response_model=InferenceResponse)
async def generate(
    generation_type: str,
    body: InferenceRequest,
    request: Request,
) -> InferenceResponse:
    """Execute a fully-resolved InferenceRequest and return InferenceResponse."""
    _verify_token(request)

    try:
        gt = GenerationType(generation_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown generation_type '{generation_type}'. Valid: {[e.value for e in GenerationType]}",
        )

    if body.generation_type != gt:
        raise HTTPException(
            status_code=400,
            detail=f"Path generation_type '{generation_type}' does not match body '{body.generation_type.value}'",
        )

    logger.info(
        "generate request_id=%s type=%s provider=%s",
        body.request_id,
        gt.value,
        body.model_policy.provider,
    )
    return await _executor.execute(body)
