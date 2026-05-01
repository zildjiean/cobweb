"""Phase 2 — vulnerability lifecycle tests."""

from __future__ import annotations

import pytest

from cobweb.api.v1 import projects as projects_router


@pytest.fixture(autouse=True)
def stub_verify(monkeypatch):
    async def _ok(*_a, **_kw):
        return "well_known_file"

    monkeypatch.setattr(projects_router, "verify_target", _ok)
    yield


WORKER = {"X-Worker-Token": "dev-worker-token-change-me"}


async def _setup_scan(client) -> tuple[str, str, str]:
    """Returns (auth_header_value, target_id, scan_id with finding ingested)."""
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "v@example.com",
            "password": "Sup3rSecretPassw0rd!",
            "full_name": "V",
            "org_name": "VCo",
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
                "template_id": "exposed-panels/admin",
                "name": "Admin panel exposed",
                "severity": "high",
                "matched_at": "https://example.com/admin",
            }
        ],
    )
    return auth, tid, sid


async def test_finding_creates_vulnerability(client):
    auth, tid, sid = await _setup_scan(client)
    h = {"authorization": auth}

    r = await client.get("/api/v1/vulnerabilities", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1
    v = body[0]
    assert v["state"] == "new"
    assert v["severity"] == "high"
    assert v["template_id"] == "exposed-panels/admin"
    assert v["sla_due_at"] is not None  # high → 14d SLA
    assert v["first_seen_scan_id"] == sid
    assert v["last_seen_scan_id"] == sid


async def test_lifecycle_transitions(client):
    auth, _tid, _sid = await _setup_scan(client)
    h = {"authorization": auth}

    vid = (await client.get("/api/v1/vulnerabilities", headers=h)).json()[0]["id"]

    # NEW → TRIAGED
    r = await client.post(
        f"/api/v1/vulnerabilities/{vid}/transition",
        json={"state": "triaged"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "triaged"

    # TRIAGED → IN_PROGRESS
    r = await client.post(
        f"/api/v1/vulnerabilities/{vid}/transition",
        json={"state": "in_progress"},
        headers=h,
    )
    assert r.json()["state"] == "in_progress"

    # IN_PROGRESS → RESOLVED
    r = await client.post(
        f"/api/v1/vulnerabilities/{vid}/transition",
        json={"state": "resolved"},
        headers=h,
    )
    assert r.json()["state"] == "resolved"

    # RESOLVED → VERIFIED
    r = await client.post(
        f"/api/v1/vulnerabilities/{vid}/transition",
        json={"state": "verified"},
        headers=h,
    )
    assert r.json()["state"] == "verified"

    # invalid transition: VERIFIED → NEW (must go REGRESSION via re-find)
    r = await client.post(
        f"/api/v1/vulnerabilities/{vid}/transition",
        json={"state": "new"},
        headers=h,
    )
    assert r.status_code == 400


async def test_regression_when_verified_vuln_resurfaces(client):
    auth, tid, _ = await _setup_scan(client)
    h = {"authorization": auth}

    vid = (await client.get("/api/v1/vulnerabilities", headers=h)).json()[0]["id"]

    # walk to verified
    for s in ("triaged", "in_progress", "resolved", "verified"):
        await client.post(
            f"/api/v1/vulnerabilities/{vid}/transition",
            json={"state": s},
            headers=h,
        )

    # second scan re-finds the same finding (same dedupe_hash) → REGRESSION
    r = await client.post(
        "/api/v1/scans",
        json={"target_id": tid, "profile": "quick", "engine": "nuclei"},
        headers=h,
    )
    sid2 = r.json()["id"]

    r = await client.post(
        f"/api/v1/scans/{sid2}/_worker/findings",
        headers=WORKER,
        json=[
            {
                "template_id": "exposed-panels/admin",
                "name": "Admin panel exposed",
                "severity": "high",
                "matched_at": "https://example.com/admin",
            }
        ],
    )
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/vulnerabilities/{vid}", headers=h)
    assert r.json()["state"] == "regression"


async def test_false_positive_skips_lifecycle(client):
    auth, _tid, _sid = await _setup_scan(client)
    h = {"authorization": auth}
    vid = (await client.get("/api/v1/vulnerabilities", headers=h)).json()[0]["id"]

    r = await client.post(
        f"/api/v1/vulnerabilities/{vid}/transition",
        json={"state": "false_positive", "notes": "Out of scope"},
        headers=h,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "false_positive"
    assert body["notes"] == "Out of scope"


async def test_accepted_risk_requires_until(client):
    auth, _tid, _sid = await _setup_scan(client)
    h = {"authorization": auth}
    vid = (await client.get("/api/v1/vulnerabilities", headers=h)).json()[0]["id"]

    # missing accepted_until
    r = await client.post(
        f"/api/v1/vulnerabilities/{vid}/transition",
        json={"state": "accepted_risk"},
        headers=h,
    )
    assert r.status_code == 400

    # with valid until
    r = await client.post(
        f"/api/v1/vulnerabilities/{vid}/transition",
        json={"state": "accepted_risk", "accepted_until": "2027-01-01T00:00:00Z"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["accepted_until"].startswith("2027-01-01")
