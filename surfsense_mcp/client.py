"""SurfSense HTTP client wiring for MCP tools."""

import os
from typing import NamedTuple

import httpx
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.dependencies import get_access_token
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30.0


class SurfSenseClientContext(NamedTuple):
    """An authenticated httpx client bound to the user's SurfSense backend."""

    client: httpx.AsyncClient
    base_url: str


def _resolve_token() -> str:
    """Pull the JWT from the validated request context (HTTP) or env (stdio)."""
    try:
        stored: AccessToken | None = get_access_token()
    except RuntimeError:
        stored = None

    if stored and stored.token:
        return stored.token

    env_token = os.getenv("SURFSENSE_JWT", "")
    if not env_token:
        raise RuntimeError(
            "No SurfSense JWT available. Set SURFSENSE_JWT (stdio) or send "
            "an Authorization: Bearer <jwt> header (http)."
        )
    return env_token


def get_surfsense_client_context() -> SurfSenseClientContext:
    """Return an httpx client configured with base URL + Bearer auth.

    The caller is responsible for closing the client (use as an async context
    manager).
    """
    base_url = os.getenv("SURFSENSE_BASE_URL", "").rstrip("/")
    if not base_url:
        raise RuntimeError("SURFSENSE_BASE_URL is not configured")

    token = _resolve_token()
    client = httpx.AsyncClient(
        base_url=base_url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    return SurfSenseClientContext(client=client, base_url=base_url)
