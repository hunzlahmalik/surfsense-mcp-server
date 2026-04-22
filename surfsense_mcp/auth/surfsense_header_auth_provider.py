"""Header-based JWT auth provider for the SurfSense MCP Server.

SurfSense does not issue long-lived API keys — the only credential a machine
client can present is a short-lived user JWT. This verifier validates a token
by calling `GET {SURFSENSE_BASE_URL}/users/me`; any 200 response means the
token is currently valid for this user.
"""

import os
import time

import httpx
from fastmcp.server.auth import TokenVerifier
from fastmcp.server.auth.auth import AccessToken
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_SESSION_TTL_SECONDS = 3600


class SurfSenseHeaderAuthProvider(TokenVerifier):
    """Validate an inbound Bearer JWT against SurfSense's `/users/me` endpoint."""

    def __init__(self, required_scopes: list[str] | None = None, timeout_seconds: float = 10.0):
        super().__init__(required_scopes=required_scopes)
        self.timeout_seconds = timeout_seconds

    def _base_url(self) -> str:
        base_url = os.getenv("SURFSENSE_BASE_URL", "").rstrip("/")
        if not base_url:
            raise RuntimeError("SURFSENSE_BASE_URL is not configured")
        return base_url

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token:
            return None

        try:
            base_url = self._base_url()
        except RuntimeError as e:
            logger.error("Cannot verify token: %s", e)
            return None

        url = f"{base_url}/users/me"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.RequestError as e:
            logger.warning("SurfSense token verification request failed: %s", e)
            return None

        if response.status_code != 200:
            logger.info(
                "SurfSense token verification failed: status=%s body=%s",
                response.status_code,
                response.text[:200],
            )
            return None

        user_data = response.json() if response.content else {}
        user_id = str(user_data.get("id") or "unknown")

        return AccessToken(
            token=token,
            client_id=user_id,
            scopes=["read"],
            expires_at=int(time.time() + _DEFAULT_SESSION_TTL_SECONDS),
            claims={
                "auth_method": "jwt_header",
                "sub": user_id,
                "email": user_data.get("email"),
            },
        )
