"""Phase 4 — report generation tests (HTML only; PDF needs Pango on host)."""

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


async def _setup_completed_scan(client) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "r@example.com",
            "password": "Sup3rSecretPassw0rd!",
            "full_name": "R",
            "org_name": "RCo",
        },
    )
    auth = f"Bearer {r.json()['access_token']}"
    h = {"authorization": auth}
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
    await client.post(f"/api/v1/targets/{tid}/verify", headers=h)
    r = await client.post(
        "/api/v1/scans",
        json={"target_id": tid, "profile": "quick", "engine": "nuclei"},
        headers=h,
    )
    sid = r.json()["id"]
    await client.post(
        f"/api/v1/scans/{sid}/_worker/findings",
        headers=WORKER,
        json=[
            {
                "template_id": "sqli/error-based",
                "name": "SQL injection",
                "severity": "critical",
                "matched_at": "/login",
            },
            {
                "template_id": "tls/weak-cipher",
                "name": "Weak TLS cipher",
                "severity": "medium",
                "matched_at": "/",
            },
        ],
    )
    await client.post(
        f"/api/v1/scans/{sid}/_worker/status", headers=WORKER, json={"status": "running"}
    )
    await client.post(
        f"/api/v1/scans/{sid}/_worker/status",
        headers=WORKER, json={"status": "completed", "progress": 100},
    )
    return auth, sid


async def test_html_technical_report(client):
    auth, sid = await _setup_completed_scan(client)
    h = {"authorization": auth}

    r = await client.get(f"/api/v1/scans/{sid}/report?kind=technical&fmt=html", headers=h)
    assert r.status_code == 200, r.text
    assert "Cobweb" in r.text
    assert "SQL injection" in r.text
    assert "Weak TLS cipher" in r.text


async def test_owasp_mapping_appears(client):
    auth, sid = await _setup_completed_scan(client)
    h = {"authorization": auth}

    r = await client.get(f"/api/v1/scans/{sid}/report?kind=owasp&fmt=html", headers=h)
    assert r.status_code == 200
    # SQLi should map to A03:2021
    assert "A03:2021" in r.text
    # TLS should map to A02:2021
    assert "A02:2021" in r.text
