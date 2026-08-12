"""Authentication API endpoints proxying to SPICE auth-service."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from platform_service.auth.spice_session_service import SpiceSessionService

router = APIRouter(tags=["authentication"])


@router.post("/auth/session")
async def create_session(request: Request) -> Response:
    """Proxy session authentication operation to SPICE auth-service and forward response cookies."""
    service = SpiceSessionService()
    return await service.handle_session_request(request)
