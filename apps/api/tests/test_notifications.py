"""Phase 3 — notification dispatcher tests."""

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


async def _setup_target(client) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "n@example.com",
            "password": "Sup3rSecretPassw0rd!",
            "full_name": "N",
            "org_name": "NCo",
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
    return auth, tid


async def test_notification_rule_crud(client):
    auth, _ = await _setup_target(client)
    h = {"authorization": auth}

    r = await client.post(
        "/api/v1/notification-rules",
        json={
            "channel": "slack",
            "target": "https://hooks.slack.com/test",
            "severity_threshold": "high",
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    rule_id = r.json()["id"]

    r = await client.get("/api/v1/notification-rules", headers=h)
    assert any(x["id"] == rule_id for x in r.json())

    r = await client.delete(f"/api/v1/notification-rules/{rule_id}", headers=h)
    assert r.status_code == 204


async def test_dispatch_fires_on_completion(client, monkeypatch):
    auth, tid = await _setup_target(client)
    h = {"authorization": auth}

    sent: list[dict] = []

    from cobweb.services import notifications as notif

    async def fake_send(self, rule, payload):  # type: ignore[no-redef]
        sent.append({"target": rule.target, "payload": payload})

    monkeypatch.setattr(notif.WebhookAdapter, "send", fake_send)

    # rule for org
    await client.post(
        "/api/v1/notification-rules",
        json={
            "channel": "webhook",
            "target": "https://example.test/hook",
            "severity_threshold": "high",
        },
        headers=h,
    )

    # create scan and ingest a high finding
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
                "template_id": "tpl-x",
                "name": "X",
                "severity": "high",
                "matched_at": "/x",
            }
        ],
    )
    # mark running, then completed
    await client.post(
        f"/api/v1/scans/{sid}/_worker/status",
        headers=WORKER,
        json={"status": "running", "progress": 10},
    )
    r = await client.post(
        f"/api/v1/scans/{sid}/_worker/status",
        headers=WORKER,
        json={"status": "completed", "progress": 100},
    )
    assert r.status_code == 200, r.text
    assert any(s["target"] == "https://example.test/hook" for s in sent)


async def test_dispatch_skips_below_threshold(client, monkeypatch):
    auth, tid = await _setup_target(client)
    h = {"authorization": auth}

    sent: list[dict] = []

    from cobweb.services import notifications as notif

    async def fake_send(self, rule, payload):  # type: ignore[no-redef]
        sent.append({"target": rule.target})

    monkeypatch.setattr(notif.WebhookAdapter, "send", fake_send)

    await client.post(
        "/api/v1/notification-rules",
        json={
            "channel": "webhook",
            "target": "https://example.test/hook",
            "severity_threshold": "critical",  # only critical fires
        },
        headers=h,
    )

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
            {"template_id": "t", "name": "Low", "severity": "low", "matched_at": "/"},
        ],
    )
    await client.post(
        f"/api/v1/scans/{sid}/_worker/status",
        headers=WORKER,
        json={"status": "running"},
    )
    await client.post(
        f"/api/v1/scans/{sid}/_worker/status",
        headers=WORKER,
        json={"status": "completed", "progress": 100},
    )
    # No webhook should have fired
    assert sent == []
