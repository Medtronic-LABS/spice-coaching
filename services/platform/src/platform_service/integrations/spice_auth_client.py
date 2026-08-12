"""HTTP client for SPICE auth-service token validation."""

from __future__ import annotations

import asyncio
import logging
from http.cookiejar import CookieJar

import httpx

from platform_service.auth.spice_context import SpiceContexts
from platform_service.config import get_settings

logger = logging.getLogger(__name__)

BEARER_PREFIX = "Bearer "
# Middleware hits ``/authenticate`` on every request; retry only transient
# failures (timeout / connection / 5xx). Auth rejections (4xx) are not retried.
_AUTHENTICATE_MAX_ATTEMPTS = 3
_AUTHENTICATE_RETRY_DELAY_SECONDS = 0.05


class _NoStoreCookieJar(CookieJar):
    """Cookie jar that refuses to store cookies.

    httpx wraps a ``Cookies`` instance into a plain ``Cookies`` via
    ``Cookies(cookies)``, which drops any ``extract_cookies`` override on a
    subclass. Passing a raw CookieJar is kept as ``self.jar``, so rejecting
    ``set_cookie`` actually prevents Set-Cookie persistence on the shared
    client (which would otherwise poison later ``/authenticate`` calls).
    """

    def set_cookie(self, cookie, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        return


class SpiceAuthError(Exception):
    """Raised when token validation fails or auth-service is unavailable."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class SpiceAuthClient:
    """Calls auth-service ``POST /authenticate`` with forwarded caller headers."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        default_client: str | None = None,
    ) -> None:
        settings = get_settings()
        base = (base_url or settings.spice_auth_base_url).rstrip("/")
        self._authenticate_url = f"{base}/authenticate"
        self._session_url = f"{base}/session"
        self._timeout = timeout if timeout is not None else settings.spice_auth_timeout_seconds
        self._default_client = default_client or settings.spice_auth_default_client
        # Shared process client must not store Spice session cookies; otherwise they
        # are auto-attached on the next /authenticate and can trigger Spice 400s.
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            cookies=_NoStoreCookieJar(),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def validate_authorization_header(authorization: str | None) -> str:
        if not authorization or not authorization.startswith(BEARER_PREFIX):
            raise SpiceAuthError(401, "missing or invalid Authorization header")
        token = authorization[len(BEARER_PREFIX) :].strip()
        if not token:
            raise SpiceAuthError(401, "missing or invalid Authorization header")
        return authorization

    async def authenticate(
        self,
        *,
        authorization: str,
        client: str | None = None,
        auth_cookie: str | None = None,
    ) -> SpiceContexts:
        """Validate the bearer token with auth-service and return user contexts."""
        self.validate_authorization_header(authorization)
        headers: dict[str, str] = {
            "Authorization": authorization,
            "client": (client or "").strip() or self._default_client,
        }
        if auth_cookie:
            headers["auth-cookie"] = auth_cookie

        last_error: SpiceAuthError | None = None
        for attempt in range(1, _AUTHENTICATE_MAX_ATTEMPTS + 1):
            try:
                resp = await self._client.post(self._authenticate_url, headers=headers)
            except httpx.TimeoutException as exc:
                last_error = SpiceAuthError(503, "authentication service unavailable")
                logger.warning(
                    "spice auth-service timeout attempt=%d/%d: %s",
                    attempt,
                    _AUTHENTICATE_MAX_ATTEMPTS,
                    exc,
                )
                if attempt < _AUTHENTICATE_MAX_ATTEMPTS:
                    await asyncio.sleep(_AUTHENTICATE_RETRY_DELAY_SECONDS)
                    continue
                raise last_error from exc
            except httpx.RequestError as exc:
                last_error = SpiceAuthError(503, "authentication service unavailable")
                logger.warning(
                    "spice auth-service unreachable attempt=%d/%d: %s",
                    attempt,
                    _AUTHENTICATE_MAX_ATTEMPTS,
                    exc,
                )
                if attempt < _AUTHENTICATE_MAX_ATTEMPTS:
                    await asyncio.sleep(_AUTHENTICATE_RETRY_DELAY_SECONDS)
                    continue
                raise last_error from exc

            if resp.status_code >= 500:
                last_error = SpiceAuthError(503, "authentication service unavailable")
                logger.warning(
                    "spice auth-service returned %s attempt=%d/%d: %s",
                    resp.status_code,
                    attempt,
                    _AUTHENTICATE_MAX_ATTEMPTS,
                    resp.text[:200],
                )
                if attempt < _AUTHENTICATE_MAX_ATTEMPTS:
                    await asyncio.sleep(_AUTHENTICATE_RETRY_DELAY_SECONDS)
                    continue
                raise last_error

            if resp.status_code >= 400:
                raise SpiceAuthError(401, "invalid or expired token")

            return SpiceContexts.model_validate(resp.json())

        assert last_error is not None
        raise last_error

    async def create_session(
        self,
        *,
        headers: dict[str, str] | None = None,
        content: bytes | str | None = None,
    ) -> httpx.Response:
        """Call auth-service ``POST /session`` with caller headers and body."""
        req_headers = dict(headers) if headers else {}
        if "client" not in req_headers or not (req_headers.get("client") or "").strip():
            req_headers["client"] = self._default_client

        try:
            resp = await self._client.post(
                self._session_url,
                headers=req_headers,
                content=content,
            )
            return resp
        except httpx.TimeoutException as exc:
            logger.error("spice auth-service session timeout: %s", exc)
            raise SpiceAuthError(503, "authentication service unavailable") from exc
        except httpx.RequestError as exc:
            logger.error("spice auth-service session unreachable: %s", exc)
            raise SpiceAuthError(503, "authentication service unavailable") from exc
