"""Phase 1 scan flow integration tests.

External target verification is stubbed; queue/pubsub are stubbed in conftest.
"""

from __future__ import annotations

import pytest

from cobweb.api.v1 import projects as projects_router


@pytest.fixture(autouse=True)
def stub_verify(monkeypatch):
    """Skip real HTTP probing of target.base_url in verify endpoint."""

    async def _ok(*_args, **_kwargs):
        return "well_known_file"

    monkeypatch.setattr(projects_router, "verify_target", _ok)
    yield


async def _bootstrap(client) -> dict[str, str]:
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "scan@example.com",
            "password": "Sup3rSecretPassw0rd!",
            "full_name": "Scan",
            "org_name": "ScanCo",
        },
    )
    assert r.status_code == 201, r.text
    headers = {"authorization": f"Bearer {r.json()['access_token']}"}

    r = await client.post(
        "/api/v1/projects",
        json={"name": "App", "slug": "app", "description": ""},
        headers=headers,
    )
    project_id = r.json()["id"]

    r = await client.post(
        f"/api/v1/projects/{project_id}/targets",
        json={"name": "prod", "base_url": "https://example.com"},
        headers=headers,
    )
    target_id = r.json()["id"]

    r = await client.post(f"/api/v1/targets/{target_id}/verify", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "verified"

    return {"headers_auth": headers["authorization"], "project_id": project_id, "target_id": target_id}


async def test_scan_create_blocks_unverified_target(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "u@example.com",
            "password": "Sup3rSecretPassw0rd!",
            "full_name": "U",
            "org_name": "UCo",
        },
    )
    h = {"authorization": f"Bearer {r.json()['access_token']}"}
    r = await client.post(
        "/api/v1/projects",
        json={"name": "P", "slug": "p", "description": ""},
        headers=h,
    )
    pid = r.json()["id"]
    r = await client.post(
        f"/api/v1/projects/{pid}/targets",
        json={"name": "t", "base_url": "https://example.com"},
        headers=h,
    )
    tid = r.json()["id"]

    r = await client.post(
        "/api/v1/scans",
        json={"target_id": tid, "profile": "quick", "engine": "nuclei"},
        headers=h,
    )
    assert r.status_code == 400
    assert "verified" in r.json()["detail"].lower()


async def test_scan_lifecycle(client):
    ctx = await _bootstrap(client)
    h = {"authorization": ctx["headers_auth"]}

    r = await client.post(
        "/api/v1/scans",
        json={"target_id": ctx["target_id"], "profile": "quick", "engine": "nuclei"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    scan = r.json()
    assert scan["status"] == "queued"
    assert scan["progress"] == 0
    assert scan["summary"] == {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    sid = scan["id"]

    # list
    r = await client.get("/api/v1/scans", headers=h)
    assert r.status_code == 200
    assert any(s["id"] == sid for s in r.json())

    # worker: queued → running
    r = await client.post(
        f"/api/v1/scans/{sid}/_worker/status",
        headers={"X-Worker-Token": "dev-worker-token-change-me"},
        json={"status": "running", "progress": 10, "template_version": "v9.0.0"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "running"

    # worker: ingest two findings
    r = await client.post(
        f"/api/v1/scans/{sid}/_worker/findings",
        headers={"X-Worker-Token": "dev-worker-token-change-me"},
        json=[
            {
                "template_id": "exposed-panels/admin-panel",
                "name": "Admin panel exposed",
                "severity": "high",
                "matched_at": "https://example.com/admin",
            },
            {
                "template_id": "tech/server-headers",
                "name": "Server header info",
                "severity": "info",
                "matched_at": "https://example.com",
            },
        ],
    )
    assert r.status_code == 200, r.text
    assert len(r.json()) == 2

    # findings list shows them
    r = await client.get(f"/api/v1/scans/{sid}/findings", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert {f["severity"] for f in body} == {"high", "info"}
    assert all(f["dedupe_hash"] for f in body)

    # finish
    r = await client.post(
        f"/api/v1/scans/{sid}/_worker/status",
        headers={"X-Worker-Token": "dev-worker-token-change-me"},
        json={"status": "completed", "progress": 100},
    )
    assert r.status_code == 200, r.text
    final = r.json()
    assert final["status"] == "completed"
    assert final["progress"] == 100
    assert final["summary"]["high"] == 1
    assert final["summary"]["info"] == 1


async def test_worker_token_required(client):
    ctx = await _bootstrap(client)
    h = {"authorization": ctx["headers_auth"]}
    r = await client.post(
        "/api/v1/scans",
        json={"target_id": ctx["target_id"], "profile": "quick", "engine": "nuclei"},
        headers=h,
    )
    sid = r.json()["id"]

    # no token
    r = await client.post(f"/api/v1/scans/{sid}/_worker/status", json={"status": "running"})
    assert r.status_code == 401

    # wrong token
    r = await client.post(
        f"/api/v1/scans/{sid}/_worker/status",
        headers={"X-Worker-Token": "nope"},
        json={"status": "running"},
    )
    assert r.status_code == 401


async def test_scan_blocks_localhost_target(client):
    """Even a verified target with a blocked URL should be rejected at scan time."""
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "lh@example.com",
            "password": "Sup3rSecretPassw0rd!",
            "full_name": "LH",
            "org_name": "LHCo",
        },
    )
    h = {"authorization": f"Bearer {r.json()['access_token']}"}
    r = await client.post(
        "/api/v1/projects",
        json={"name": "P", "slug": "p", "description": ""},
        headers=h,
    )
    pid = r.json()["id"]
    r = await client.post(
        f"/api/v1/projects/{pid}/targets",
        json={"name": "lh", "base_url": "http://127.0.0.1:8080"},
        headers=h,
    )
    tid = r.json()["id"]
    r = await client.post(f"/api/v1/targets/{tid}/verify", headers=h)
    assert r.status_code == 200

    r = await client.post(
        "/api/v1/scans",
        json={"target_id": tid, "profile": "quick", "engine": "nuclei"},
        headers=h,
    )
    assert r.status_code == 400
    assert "blocked" in r.json()["detail"].lower()
