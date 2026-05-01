"""OIDC SSO via Authlib.

Flow:
    1. GET  /api/v1/auth/oidc/login      → 302 to provider /authorize
    2.       provider → /oidc/callback   (front-channel)
    3. POST /api/v1/auth/oidc/exchange   { code, state } → access/refresh tokens

The frontend handles the redirect on /oidc/callback and POSTs to /exchange.
On first login, a User+Org+Member is auto-provisioned from the email/name claims.
"""

from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

from cobweb.core.settings import Settings


class OidcError(ValueError):
    pass


class OidcService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._discovery_cache: dict[str, Any] | None = None

    @property
    def configured(self) -> bool:
        return bool(
            self._settings.oidc_client_id
            and self._settings.oidc_client_secret
            and self._settings.oidc_discovery_url
        )

    async def discovery(self) -> dict[str, Any]:
        if self._discovery_cache is not None:
            return self._discovery_cache
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(self._settings.oidc_discovery_url)
            r.raise_for_status()
            self._discovery_cache = r.json()
        return self._discovery_cache

    async def authorize_url(self) -> tuple[str, str]:
        if not self.configured:
            raise OidcError("OIDC not configured")
        disc = await self.discovery()
        state = secrets.token_urlsafe(24)
        params = {
            "response_type": "code",
            "client_id": self._settings.oidc_client_id,
            "redirect_uri": self._settings.oidc_redirect_uri,
            "scope": "openid email profile",
            "state": state,
        }
        url = f"{disc['authorization_endpoint']}?{urlencode(params)}"
        return url, state

    async def exchange_code(self, code: str) -> dict[str, Any]:
        if not self.configured:
            raise OidcError("OIDC not configured")
        disc = await self.discovery()
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(
                disc["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._settings.oidc_redirect_uri,
                    "client_id": self._settings.oidc_client_id,
                    "client_secret": self._settings.oidc_client_secret,
                },
            )
            if r.status_code >= 300:
                raise OidcError(f"token exchange failed: {r.text}")
            tokens = r.json()
            access = tokens.get("access_token")
            if not access:
                raise OidcError("no access_token in response")
            ru = await c.get(
                disc["userinfo_endpoint"],
                headers={"Authorization": f"Bearer {access}"},
            )
            if ru.status_code >= 300:
                raise OidcError(f"userinfo failed: {ru.text}")
            return ru.json()
