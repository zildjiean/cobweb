"""Phase 2 — scan diff tests (NEW / FIXED / RECURRING / REGRESSION)."""

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


async def _bootstrap(client) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "d@example.com",
            "password": "Sup3rSecretPassw0rd!",
            "full_name": "D",
            "org_name": "DCo",
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
    return auth, tid


async def _new_scan_with_findings(client, auth, tid, findings) -> str:
    r = await client.post(
        "/api/v1/scans",
        json={"target_id": tid, "profile": "quick", "engine": "nuclei"},
        headers={"authorization": auth},
    )
    sid = r.json()["id"]
    if findings:
        r = await client.post(
            f"/api/v1/scans/{sid}/_worker/findings",
            headers=WORKER,
            json=findings,
        )
        assert r.status_code == 200
    return sid


async def test_diff_categorizes_correctly(client):
    auth, tid = await _bootstrap(client)
    h = {"authorization": auth}

    # Scan 1: A, B (high), C (medium)
    sid1 = await _new_scan_with_findings(client, auth, tid, [
        {"template_id": "tpl-a", "name": "A", "severity": "high", "matched_at": "/a"},
        {"template_id": "tpl-b", "name": "B", "severity": "high", "matched_at": "/b"},
        {"template_id": "tpl-c", "name": "C", "severity": "medium", "matched_at": "/c"},
    ])

    # Scan 2: A (recurring), C (recurring), D (new). B is fixed.
    sid2 = await _new_scan_with_findings(client, auth, tid, [
        {"template_id": "tpl-a", "name": "A", "severity": "high", "matched_at": "/a"},
        {"template_id": "tpl-c", "name": "C", "severity": "medium", "matched_at": "/c"},
        {"template_id": "tpl-d", "name": "D", "severity": "low", "matched_at": "/d"},
    ])

    r = await client.get(f"/api/v1/scans/{sid2}/diff", headers=h)
    assert r.status_code == 200, r.text
    diff = r.json()
    assert diff["base_scan_id"] == sid1
    assert diff["head_scan_id"] == sid2

    new_tpl = {e["template_id"] for e in diff["new"]}
    fixed_tpl = {e["template_id"] for e in diff["fixed"]}
    recurring_tpl = {e["template_id"] for e in diff["recurring"]}
    assert new_tpl == {"tpl-d"}
    assert fixed_tpl == {"tpl-b"}
    assert recurring_tpl == {"tpl-a", "tpl-c"}


async def test_diff_marks_regression_when_vuln_was_verified(client):
    auth, tid = await _bootstrap(client)
    h = {"authorization": auth}

    sid1 = await _new_scan_with_findings(client, auth, tid, [
        {"template_id": "tpl-a", "name": "A", "severity": "high", "matched_at": "/a"},
    ])
    # walk vuln to verified
    vid = (await client.get("/api/v1/vulnerabilities", headers=h)).json()[0]["id"]
    for s in ("triaged", "in_progress", "resolved", "verified"):
        await client.post(
            f"/api/v1/vulnerabilities/{vid}/transition",
            json={"state": s}, headers=h,
        )

    sid2 = await _new_scan_with_findings(client, auth, tid, [
        {"template_id": "tpl-a", "name": "A", "severity": "high", "matched_at": "/a"},
    ])

    r = await client.get(f"/api/v1/scans/{sid2}/diff", headers=h)
    diff = r.json()
    regression_tpl = {e["template_id"] for e in diff["regression"]}
    assert "tpl-a" in regression_tpl
