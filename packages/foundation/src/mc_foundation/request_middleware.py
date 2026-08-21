"""ASGI middleware for request correlation IDs and access logs."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Sequence

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from mc_foundation.logging import get_access_logger
from mc_foundation.tracing import new_request_id

REQUEST_ID_HEADER = "X-Request-ID"
_DEFAULT_EXCLUDE_SUFFIXES: tuple[str, ...] = ("health", "ready")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a request ID to every HTTP request and emit one access log line."""

    def __init__(
        self,
        app,
        *,
        service_name: str = "microcoaching",
        exclude_path_suffixes: Sequence[str] = _DEFAULT_EXCLUDE_SUFFIXES,
    ) -> None:
        super().__init__(app)
        self._service_name = service_name
        self._exclude_path_suffixes = frozenset(suffix.lower() for suffix in exclude_path_suffixes)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming.strip() if incoming and incoming.strip() else new_request_id()
        request.state.request_id = request_id
        started = time.monotonic()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            self._emit_access(request, request_id, status, started)
            raise
        self._emit_access(request, request_id, status, started)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    def _emit_access(
        self,
        request: Request,
        request_id: str,
        status: int,
        started: float,
    ) -> None:
        path = request.url.path
        if _path_suffix(path) in self._exclude_path_suffixes:
            return
        latency_ms = int((time.monotonic() - started) * 1000)
        get_access_logger().info(
            "access",
            extra={
                "method": request.method,
                "path": path,
                "status": status,
                "latency_ms": latency_ms,
                "request_id": request_id,
                "user_id": _user_id_from_request(request),
                "service": self._service_name,
            },
        )


def _path_suffix(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1].lower()


def _user_id_from_request(request: Request) -> int | str | None:
    user = getattr(request.state, "spice_user", None)
    if user is None:
        return None
    return getattr(user, "id", None)
