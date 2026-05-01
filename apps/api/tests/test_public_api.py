"""Phase 3 — public API + token CRUD."""

from __future__ import annotations

import pytest

from cobweb.api.v1 import projects as projects_router

WORKER = {"X-Worker-Token": "dev-worker-token-change-me"}


@pytest.fixture(autouse=True)
def stub_verify(monkeypatch):
    async def _ok(*_a, **_kw):
        return "well_known_file"

    monkeypatch.setattr(projects_router, "verify_target", _ok)
    yield


async def _setup(client) -> tuple[str, str, str]:
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "ci@example.com",
            "password": "Sup3rSecretPassw0rd!",
            "full_name": "CI",
            "org_name": "CICo",
        },
    )
    auth = f"Bearer {r.json()['access_token']}"
    h = {"authorization": auth}
    r = await client.post(
        "/api/v1/projects",
        json={"name": "P", "slug": "p", "description": ""}, headers=h,
    )
    pid = r.json()["id"]
    r = await client.post(
        f"/api/v1/projects/{pid}/targets",
        json={"name": "t", "base_url": "https://example.com"}, headers=h,
    )
    tid = r.json()["id"]
    await client.post(f"/api/v1/targets/{tid}/verify", headers=h)
    return auth, pid, tid


async def test_token_lifecycle(client):
    auth, _, _ = await _setup(client)
    h = {"authorization": auth}

    # create
    r = await client.post(
        "/api/v1/tokens", json={"name": "ci-pipeline"}, headers=h,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["plaintext"].startswith("cwbk_")
    tid = body["id"]
    plaintext = body["plaintext"]

    # list
    r = await client.get("/api/v1/tokens", headers=h)
    assert any(t["id"] == tid for t in r.json())

    # plaintext is not visible on list (only on creation)
    assert "plaintext" not in r.json()[0]

    # revoke
    r = await client.delete(f"/api/v1/tokens/{tid}", headers=h)
    assert r.status_code == 204

    # token rejected after revoke
    r = await client.post(
        "/public/v1/scans",
        headers={"X-Api-Key": plaintext},
        json={"target_url": "https://example.com", "wait": False},
    )
    assert r.status_code == 401


async def test_public_scan_rejects_unverified_url(client):
    auth, _, _ = await _setup(client)
    h = {"authorization": auth}
    r = await client.post("/api/v1/tokens", json={"name": "ci"}, headers=h)
    plaintext = r.json()["plaintext"]

    # URL not registered as a target
    r = await client.post(
        "/public/v1/scans",
        headers={"X-Api-Key": plaintext},
        json={"target_url": "https://other.example.com", "wait": False},
    )
    assert r.status_code == 404


async def test_public_scan_creates_scan(client):
    auth, _, _ = await _setup(client)
    h = {"authorization": auth}
    r = await client.post("/api/v1/tokens", json={"name": "ci"}, headers=h)
    plaintext = r.json()["plaintext"]

    r = await client.post(
        "/public/v1/scans",
        headers={"X-Api-Key": plaintext},
        json={
            "target_url": "https://example.com",
            "profile": "quick",
            "wait": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scan_id"]
    assert body["status"] == "queued"
    assert body["fail_build"] is False
