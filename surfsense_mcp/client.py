"""SurfSense HTTP client wiring for MCP tools."""

import os
import time
from threading import Lock
from typing import NamedTuple

import httpx
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.dependencies import get_access_token
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30.0
_DEFAULT_TOKEN_TTL_SECONDS = 3300  # 55 min — fastapi-users default JWT is 60 min

_cached_password_token: str | None = None
_cached_password_token_expires_at: float = 0.0
_password_token_lock = Lock()


class SurfSenseClientContext(NamedTuple):
    """An authenticated httpx client bound to the user's SurfSense backend."""

    client: httpx.AsyncClient
    base_url: str


def _base_url() -> str:
    base_url = os.getenv("SURFSENSE_BASE_URL", "").rstrip("/")
    if not base_url:
        raise RuntimeError("SURFSENSE_BASE_URL is not configured")
    return base_url


def _token_ttl_seconds() -> int:
    raw = os.getenv("TOKEN_TTL")
    if not raw:
        return _DEFAULT_TOKEN_TTL_SECONDS
    try:
        return max(60, int(raw))
    except ValueError:
        return _DEFAULT_TOKEN_TTL_SECONDS


async def _login_with_password() -> str:
    """Exchange SURFSENSE_EMAIL + SURFSENSE_PASSWORD for a JWT via fastapi-users."""
    email = os.getenv("SURFSENSE_EMAIL", "")
    password = os.getenv("SURFSENSE_PASSWORD", "")
    if not email or not password:
        raise RuntimeError("Password-login fallback requires SURFSENSE_EMAIL and SURFSENSE_PASSWORD.")

    url = f"{_base_url()}/auth/jwt/login"
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
        response = await client.post(
            url,
            data={"username": email, "password": password},
        )
    if response.status_code != 200:
        raise RuntimeError(f"SurfSense password login failed: {response.status_code} {response.text[:200]}")
    body = response.json()
    token = body.get("access_token")
    if not token:
        raise RuntimeError("SurfSense password login returned no access_token")
    logger.info("Authenticated with SurfSense via password (TTL %ds)", _token_ttl_seconds())
    return token


def _get_cached_password_token() -> str | None:
    with _password_token_lock:
        if _cached_password_token and time.time() < _cached_password_token_expires_at:
            return _cached_password_token
    return None


def _store_password_token(token: str) -> None:
    global _cached_password_token, _cached_password_token_expires_at
    with _password_token_lock:
        _cached_password_token = token
        _cached_password_token_expires_at = time.time() + _token_ttl_seconds()


def invalidate_password_token() -> None:
    """Drop the cached token so the next call forces a fresh login."""
    global _cached_password_token, _cached_password_token_expires_at
    with _password_token_lock:
        _cached_password_token = None
        _cached_password_token_expires_at = 0.0


def _has_password_creds() -> bool:
    return bool(os.getenv("SURFSENSE_EMAIL")) and bool(os.getenv("SURFSENSE_PASSWORD"))


async def _resolve_token() -> tuple[str, str]:
    """Return (token, source) where source is 'http' | 'env' | 'password'.

    Resolution order:
      1. FastMCP request-scoped token (HTTP mode, validated Bearer)
      2. SURFSENSE_JWT env var (stdio, user-paste)
      3. Password login via SURFSENSE_EMAIL + SURFSENSE_PASSWORD (stdio only)
    """
    try:
        stored: AccessToken | None = get_access_token()
    except RuntimeError:
        stored = None

    if stored and stored.token:
        return stored.token, "http"

    env_token = os.getenv("SURFSENSE_JWT", "")
    if env_token:
        return env_token, "env"

    if _has_password_creds():
        cached = _get_cached_password_token()
        if cached:
            return cached, "password"
        token = await _login_with_password()
        _store_password_token(token)
        return token, "password"

    raise RuntimeError(
        "No SurfSense credential available. Set SURFSENSE_JWT, or "
        "SURFSENSE_EMAIL + SURFSENSE_PASSWORD (stdio), or send an "
        "Authorization: Bearer <jwt> header (http)."
    )


async def get_surfsense_client_context() -> SurfSenseClientContext:
    """Return an httpx client configured with base URL + Bearer auth.

    Caller is responsible for closing the client (use as an async context
    manager). If auth came from the password fallback, a 401 mid-request
    should be handled by retrying once via ``retry_with_fresh_password_token``.
    """
    base_url = _base_url()
    token, _source = await _resolve_token()
    client = httpx.AsyncClient(
        base_url=base_url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    return SurfSenseClientContext(client=client, base_url=base_url)


async def resolve_auth_header() -> tuple[str, str]:
    """Return (Authorization header value, source) for callers that manage
    their own httpx.AsyncClient (e.g. multipart upload, SSE streaming)."""
    token, source = await _resolve_token()
    return f"Bearer {token}", source


def auth_came_from_password() -> bool:
    """True iff the last call would use password-cached creds (i.e. no JWT,
    no request-scoped token, and password creds are configured)."""
    try:
        stored: AccessToken | None = get_access_token()
    except RuntimeError:
        stored = None
    if stored and stored.token:
        return False
    if os.getenv("SURFSENSE_JWT"):
        return False
    return _has_password_creds()


async def authed_request(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json: object | None = None,
) -> httpx.Response:
    """JSON request with 401-retry-once when auth came from password login.

    Every tool that hits a simple JSON endpoint should go through this
    helper so password-cached tokens get refreshed transparently.
    """

    async def _do() -> httpx.Response:
        ctx = await get_surfsense_client_context()
        async with ctx.client as client:
            return await client.request(method, path, params=params, json=json)

    response = await _do()
    if response.status_code == 401 and auth_came_from_password():
        logger.info("401 with password auth — invalidating cached token and retrying")
        invalidate_password_token()
        response = await _do()
    response.raise_for_status()
    return response


async def authed_multipart_post(
    path: str,
    *,
    files: dict[str, tuple[str, bytes, str]],
    data: dict[str, str] | None = None,
    timeout: float | None = None,
) -> httpx.Response:
    """Multipart POST with 401-retry-once. Used by document uploads.

    The JSON Content-Type from the shared client context would break
    multipart, so this helper drives its own AsyncClient.
    """
    request_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT_SECONDS

    async def _do() -> httpx.Response:
        auth, _ = await resolve_auth_header()
        async with httpx.AsyncClient(
            base_url=_base_url(),
            timeout=request_timeout,
            headers={"Authorization": auth},
        ) as client:
            return await client.post(path, files=files, data=data)

    response = await _do()
    if response.status_code == 401 and auth_came_from_password():
        logger.info("401 with password auth on multipart — invalidating and retrying")
        invalidate_password_token()
        response = await _do()
    response.raise_for_status()
    return response


class _StreamContext:
    """Async context manager that yields an httpx streaming response and
    retries once on 401 if password auth is in use.

    Use as:
        async with stream_authed_post(path, json=payload) as response:
            async for line in response.aiter_lines():
                ...
    """

    def __init__(self, path: str, json: object) -> None:
        self._path = path
        self._json = json
        self._client: httpx.AsyncClient | None = None
        self._response: httpx.Response | None = None

    async def __aenter__(self) -> httpx.Response:
        self._response = await self._open()
        if self._response.status_code == 401 and auth_came_from_password():
            logger.info("401 with password auth on SSE — invalidating and retrying")
            await self._close_active()
            invalidate_password_token()
            self._response = await self._open()
        self._response.raise_for_status()
        return self._response

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._close_active()

    async def _open(self) -> httpx.Response:
        auth, _ = await resolve_auth_header()
        self._client = httpx.AsyncClient(
            base_url=_base_url(),
            timeout=httpx.Timeout(DEFAULT_TIMEOUT_SECONDS, read=None),
            headers={
                "Authorization": auth,
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        )
        request = self._client.build_request("POST", self._path, json=self._json)
        return await self._client.send(request, stream=True)

    async def _close_active(self) -> None:
        if self._response is not None:
            try:
                await self._response.aclose()
            except Exception:
                logger.exception("Error closing streaming response")
            self._response = None
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                logger.exception("Error closing streaming client")
            self._client = None


def stream_authed_post(path: str, *, json: object) -> _StreamContext:
    """Open an SSE stream with auth + 401-retry. Caller uses `async with`."""
    return _StreamContext(path, json)
