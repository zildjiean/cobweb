"""Phase 4 — OIDC SSO tests (provider stubbed)."""

from __future__ import annotations

import pytest

from cobweb.api.v1 import auth as auth_router


@pytest.fixture
def configured_oidc(monkeypatch):
    auth_router._oidc._settings.oidc_client_id = "test-client"
    auth_router._oidc._settings.oidc_client_secret = "test-secret"
    auth_router._oidc._settings.oidc_discovery_url = "https://provider.test/.well-known/openid-configuration"

    async def fake_discovery(_self):
        return {
            "authorization_endpoint": "https://provider.test/authorize",
            "token_endpoint": "https://provider.test/token",
            "userinfo_endpoint": "https://provider.test/userinfo",
        }

    monkeypatch.setattr(auth_router._oidc.__class__, "discovery", fake_discovery)
    yield


async def test_oidc_login_returns_authorize_url(client, configured_oidc):
    r = await client.get("/api/v1/auth/oidc/login")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["authorize_url"].startswith("https://provider.test/authorize?")
    assert "state" in body


async def test_oidc_login_503_when_not_configured(client):
    auth_router._oidc._settings.oidc_client_id = ""
    r = await client.get("/api/v1/auth/oidc/login")
    assert r.status_code == 503


async def test_oidc_exchange_provisions_user(client, configured_oidc, monkeypatch):
    async def fake_exchange(_self, code):
        return {"email": "sso@example.com", "name": "SSO User"}

    monkeypatch.setattr(
        auth_router._oidc.__class__, "exchange_code", fake_exchange
    )

    r = await client.post("/api/v1/auth/oidc/exchange", json={"code": "abc"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    assert token

    # logged-in works
    r = await client.get(
        "/api/v1/auth/me",
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "sso@example.com"
    assert body["role"] == "admin"
