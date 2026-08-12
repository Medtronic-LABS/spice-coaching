"""Session authentication service for SPICE backend integration.

Proxy authentication/session creation requests to SPICE auth-service,
forward response body and status, and set the Cookie/Authorization header
on the response from Coaching platform.
"""

from __future__ import annotations

import logging

from fastapi import Request, Response

from platform_service.deps import get_spice_auth_client
from platform_service.integrations.spice_auth_client import SpiceAuthClient, SpiceAuthError

logger = logging.getLogger(__name__)

# Headers to exclude when forwarding caller request to SPICE backend
FORWARD_EXCLUDE_REQUEST_HEADERS = frozenset(
    {
        "host",
        "content-length",
        "transfer-encoding",
        "connection",
    }
)

# Headers to exclude when forwarding SPICE response to client (including content-length so Starlette calculates it once)
FORWARD_EXCLUDE_RESPONSE_HEADERS = frozenset(
    {
        "content-length",
        "transfer-encoding",
        "connection",
    }
)


def normalize_auth_cookie_value(raw: str) -> str:
    """Extract the cookie value from a bare value or Set-Cookie-style string."""
    trimmed = raw.strip()
    if not trimmed:
        return trimmed

    first_pair = trimmed.split(";", 1)[0].strip()
    if first_pair.lower().startswith("auth-cookie="):
        return first_pair.split("=", 1)[1].strip()
    return trimmed


class SpiceSessionService:
    """Service to handle session authentication via SPICE auth-service."""

    def __init__(self, client: SpiceAuthClient | None = None) -> None:
        self._client = client

    def _get_client(self) -> SpiceAuthClient:
        if self._client is not None:
            return self._client
        return get_spice_auth_client()

    async def handle_session_request(self, request: Request) -> Response:
        """Forward session request to SPICE backend, set Authorization header with cookie, and forward response."""
        client_instance = self._get_client()

        body = await request.body()
        headers: dict[str, str] = {}
        for k, v in request.headers.items():
            if k.lower() not in FORWARD_EXCLUDE_REQUEST_HEADERS:
                headers[k] = v

        try:
            spice_resp = await client_instance.create_session(
                headers=headers,
                content=body,
            )
        except SpiceAuthError as exc:
            logger.error("SPICE session authentication failed: %s", exc)
            return Response(
                content=f'{{"detail": "{exc.detail}"}}'.encode(),
                status_code=exc.status_code,
                media_type="application/json",
            )

        # Prefer auth-cookie; fall back to Set-Cookie / Cookie from SPICE.
        auth_cookie_raw = (
            spice_resp.headers.get("auth-cookie")
            or spice_resp.headers.get("set-cookie")
            or spice_resp.headers.get("cookie")
        )
        if not auth_cookie_raw:
            set_cookies = spice_resp.headers.get_list("set-cookie")
            if set_cookies:
                auth_cookie_raw = set_cookies[0]

        auth_cookie_val = normalize_auth_cookie_value(auth_cookie_raw) if auth_cookie_raw else None

        response_content = spice_resp.content
        media_type = spice_resp.headers.get("content-type") or "application/json"

        # Construct forwarded response using original body and content type
        response = Response(
            content=response_content,
            status_code=spice_resp.status_code,
            media_type=media_type,
        )

        # Preserve content-type from Response, then add auth headers the SPA can read.
        raw_headers: list[tuple[bytes, bytes]] = [
            (name.encode("latin-1"), value.encode("latin-1"))
            for name, value in response.headers.items()
            if name.lower() not in FORWARD_EXCLUDE_RESPONSE_HEADERS
        ]

        if auth_cookie_val:
            encoded = auth_cookie_val.encode("utf-8")
            raw_headers.append((b"authorization", encoded))
            raw_headers.append((b"auth-cookie", encoded))

        response.raw_headers = raw_headers
        return response
