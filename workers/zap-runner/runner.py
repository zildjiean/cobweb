"""OWASP ZAP worker — consumes scan jobs from RabbitMQ, runs spider + active scan,
streams findings to the Cobweb API.

Operational model: ZAP daemon runs in a sidecar container on the same Pod (port 8090),
this worker drives it via the ZAP REST API (using zaproxy python client).

Required env:
    COBWEB_RABBITMQ_URL
    COBWEB_API_BASE
    COBWEB_WORKER_TOKEN
    COBWEB_ZAP_HOST    (default http://localhost:8090)
    COBWEB_ZAP_APIKEY  (set via -config api.key=... when launching ZAP daemon)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

import aio_pika
import httpx
from loguru import logger

QUEUE = "cobweb.scans.zap"

ZAP_RISK_TO_SEVERITY = {
    "High": "high",
    "Medium": "medium",
    "Low": "low",
    "Informational": "info",
}

# How often to poll ZAP alerts during streaming and probe for cancel.
STREAM_TICK_SEC = 3.0
PROGRESS_POLL_SEC = 3.0

# ZAP daemon can stall briefly under heavy active-scan plugins. Tolerate transient
# errors so a single 60s timeout doesn't kill an otherwise-progressing scan.
ZAP_GET_RETRIES = 2          # retries per ZAP API call
ZAP_GET_TIMEOUT_SEC = 90.0   # raised from httpx default (was 60s, too tight)
ASCAN_MAX_CONSECUTIVE_FAILS = 4  # ascan loop bails only after N back-to-back errors


def _scrub(value: Any) -> Any:
    """Recursively strip null bytes (\\x00) from strings — Postgres TEXT rejects them."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def _normalize_alert(
    alert: dict[str, Any], message: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Normalize a ZAP alert dict into Cobweb's Finding shape.

    `message` is the optional follow-up payload from /core/view/message — it
    contains the raw HTTP request/response that triggered the alert. When
    present we surface those for the HTTP replay UI; when absent (fetch
    failed, or alert has no messageId) we fall back to evidence.
    """
    alert = _scrub(alert)
    risk = alert.get("risk") or "Informational"
    request_raw: str | None = None
    response_raw: str | None = None
    if message:
        message = _scrub(message)
        req_header = message.get("requestHeader") or ""
        req_body = message.get("requestBody") or ""
        request_raw = (req_header + (req_body or "")).strip() or None
        resp_header = message.get("responseHeader") or ""
        resp_body = message.get("responseBody") or ""
        response_raw = (resp_header + (resp_body or "")).strip() or None
    return {
        "template_id": f"zap/{alert.get('pluginId', 'unknown')}",
        "name": alert.get("name") or "ZAP alert",
        "severity": ZAP_RISK_TO_SEVERITY.get(risk, "info"),
        "matched_at": alert.get("url") or "",
        "matcher_name": alert.get("alertRef") or alert.get("alert"),
        "description": alert.get("description"),
        "remediation": alert.get("solution"),
        "cve": None,
        "cwe": str(alert.get("cweid")) if alert.get("cweid") else None,
        "cvss": None,
        "request": request_raw,
        "response": response_raw or alert.get("evidence"),
        "raw": alert,
    }


class ZapClient:
    """Thin wrapper over the ZAP REST API."""

    def __init__(self, host: str, api_key: str) -> None:
        self._host = host.rstrip("/")
        self._key = api_key

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        """GET against the ZAP REST API with retry on transient errors.

        ZAP's daemon can briefly stop accepting connections during heavy plugin
        runs (active scan with many threads). A single timeout there shouldn't
        kill the whole scan — retry a couple times with backoff before giving up.
        """
        params = {"apikey": self._key, **{k: str(v) for k, v in params.items()}}
        last_exc: Exception | None = None
        for attempt in range(ZAP_GET_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=ZAP_GET_TIMEOUT_SEC) as c:
                    r = await c.get(f"{self._host}{path}", params=params)
                    r.raise_for_status()
                    return r.json()
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.ReadError) as e:
                last_exc = e
                if attempt < ZAP_GET_RETRIES:
                    backoff = 2 ** attempt  # 1s, 2s
                    logger.warning(
                        "ZAP {} timed out (attempt {}/{}), retrying in {}s",
                        path, attempt + 1, ZAP_GET_RETRIES + 1, backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                raise
        # Unreachable but mypy doesn't know
        if last_exc:
            raise last_exc
        raise RuntimeError("unreachable")

    async def access_url(self, target: str) -> bool:
        """Force ZAP to fetch the URL once so it's in the session/sites tree.
        Required before active scan when target serves no in-page links to spider.

        Returns True only if ZAP actually got a response and added the site to its tree.
        """
        try:
            await self._get(
                "/JSON/core/action/accessUrl/", url=target, followRedirects="true"
            )
        except httpx.HTTPError:
            return False
        # Check the site actually got registered (would be missing if connect timed out)
        try:
            sites = await self._get("/JSON/core/view/sites/")
        except httpx.HTTPError:
            return False
        site_list: list[str] = sites.get("sites") or []
        from urllib.parse import urlparse

        host = urlparse(target).netloc
        return any(host in s for s in site_list)

    async def spider_start(self, target: str) -> str:
        body = await self._get("/JSON/spider/action/scan/", url=target, recurse="true")
        return str(body["scan"])

    async def spider_status(self, scan_id: str) -> int:
        body = await self._get("/JSON/spider/view/status/", scanId=scan_id)
        return int(body.get("status") or 0)

    async def spider_stop(self, scan_id: str) -> None:
        try:
            await self._get("/JSON/spider/action/stop/", scanId=scan_id)
        except httpx.HTTPError as e:
            logger.warning("spider_stop failed: {}", e)

    async def ascan_start(self, target: str) -> str:
        body = await self._get(
            "/JSON/ascan/action/scan/", url=target, recurse="true", inScopeOnly="false"
        )
        return str(body["scan"])

    async def ascan_status(self, scan_id: str) -> int:
        body = await self._get("/JSON/ascan/view/status/", scanId=scan_id)
        return int(body.get("status") or 0)

    async def ascan_stop(self, scan_id: str) -> None:
        try:
            await self._get("/JSON/ascan/action/stop/", scanId=scan_id)
        except httpx.HTTPError as e:
            logger.warning("ascan_stop failed: {}", e)

    async def alerts(self, target: str) -> list[dict[str, Any]]:
        body = await self._get("/JSON/core/view/alerts/", baseurl=target)
        return body.get("alerts") or []

    async def message(self, message_id: str) -> dict[str, Any] | None:
        """Fetch the full HTTP request/response for an alert's messageId.
        Returns None on any error so a missing message never breaks streaming."""
        try:
            body = await self._get("/JSON/core/view/message/", id=message_id)
        except (httpx.HTTPError, ValueError):
            return None
        return body.get("message")


class ApiClient:
    def __init__(self, base: str, token: str) -> None:
        self._base = base.rstrip("/")
        self._headers = {"X-Worker-Token": token, "Content-Type": "application/json"}

    async def status(self, scan_id: str, **kwargs: Any) -> None:
        url = f"{self._base}/api/v1/scans/{scan_id}/_worker/status"
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post(url, headers=self._headers, json=kwargs)
            if r.status_code >= 300:
                logger.warning("status update failed: {} {}", r.status_code, r.text)

    async def findings(self, scan_id: str, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        url = f"{self._base}/api/v1/scans/{scan_id}/_worker/findings"
        for i in range(0, len(items), 50):
            chunk = items[i : i + 50]
            async with httpx.AsyncClient(timeout=30.0) as c:
                r = await c.post(url, headers=self._headers, json=chunk)
                if r.status_code >= 300:
                    logger.warning("ingest failed: {} {}", r.status_code, r.text)

    async def is_active(self, scan_id: str) -> bool:
        """Probe whether the scan is still active. 410 GONE → cancelled/terminal.
        Fail-open on transient errors so we don't kill a scan over a flaky network."""
        url = f"{self._base}/api/v1/scans/{scan_id}/_worker/active"
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(url, headers=self._headers)
            if r.status_code == 200:
                return True
            if r.status_code == 410:
                return False
            logger.warning("active probe odd status {} {}", r.status_code, r.text)
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("active probe error: {}", e)
            return True


async def _wait_until(coro_factory, target: int, *, label: str, sleep: float = PROGRESS_POLL_SEC,
                      timeout_s: float = 1800,
                      cancel_event: asyncio.Event | None = None,
                      api: "ApiClient | None" = None,
                      scan_id: str | None = None) -> int:
    """Poll a ZAP progress endpoint until it reaches `target`.

    Between polls, also probe the API for cancel — return early (with the last
    progress value) if cancelled. Returns the final observed progress.
    """
    start = time.monotonic()
    last = 0
    while True:
        last = await coro_factory()
        logger.info("{} progress: {}%", label, last)
        if last >= target:
            return last
        if cancel_event is not None and api is not None and scan_id is not None:
            if not await api.is_active(scan_id):
                cancel_event.set()
                return last
        if time.monotonic() - start > timeout_s:
            raise TimeoutError(f"{label} timed out at {last}%")
        await asyncio.sleep(sleep)


def _alert_key(alert: dict[str, Any]) -> tuple[str, str, str, str]:
    """Stable identity for an alert across polls — ZAP doesn't expose IDs.

    pluginId + url + alertRef + evidence is precise enough that two alerts on
    the same URL with different payloads still get separate findings.
    """
    return (
        str(alert.get("pluginId", "")),
        str(alert.get("url", "")),
        str(alert.get("alertRef") or alert.get("alert") or ""),
        str(alert.get("evidence", "")),
    )


async def stream_alerts(
    api: ApiClient,
    zap: ZapClient,
    scan_id: str,
    target: str,
    stop_event: asyncio.Event,
    pre_existing_keys: set[tuple[str, str, str, str]] | None = None,
) -> int:
    """Poll /JSON/core/view/alerts/ every STREAM_TICK_SEC and POST any new ones.

    `pre_existing_keys` is a snapshot of alerts ZAP already had for this target
    BEFORE this scan started — used to filter out leftovers from prior scans on
    the same daemon (ZAP keeps alerts in the session, not per-scan). Treating
    those as already-seen prevents re-shipping them as fresh findings.

    De-duplicates by `_alert_key` so we never resend the same alert twice. Runs
    until stop_event is set, then does one final pass to catch the last batch.
    Returns the total count of unique alerts shipped.
    """
    seen: set[tuple[str, str, str, str]] = set(pre_existing_keys or ())
    total = 0

    async def _drain() -> None:
        nonlocal total
        try:
            alerts = await zap.alerts(target)
        except Exception as e:  # noqa: BLE001
            logger.warning("alerts poll failed: {}", e)
            return
        new_items: list[dict[str, Any]] = []
        for a in alerts:
            k = _alert_key(a)
            if k in seen:
                continue
            seen.add(k)
            msg_id = a.get("messageId")
            message = await zap.message(str(msg_id)) if msg_id else None
            new_items.append(_normalize_alert(a, message))
        if new_items:
            try:
                await api.findings(scan_id, new_items)
            except Exception as e:  # noqa: BLE001
                logger.warning("findings ship failed: {}", e)
                return
            total += len(new_items)
            logger.info("scan {} streamed +{} alerts (total={})", scan_id, len(new_items), total)

    while not stop_event.is_set():
        await _drain()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=STREAM_TICK_SEC)
        except asyncio.TimeoutError:
            pass
    # final pass — ZAP may have produced alerts between last tick and stop
    await _drain()
    return total


async def handle_job(api: ApiClient, zap: ZapClient, job: dict[str, Any]) -> None:
    scan_id = job["scan_id"]
    target = job["target_url"]
    logger.info("ZAP scan {} starting | target={}", scan_id, target)

    await api.status(scan_id, status="running", progress=2)
    cancel_event = asyncio.Event()
    spider_id: str | None = None
    ascan_id: str | None = None
    stream_task: asyncio.Task[int] | None = None
    stream_stop = asyncio.Event()
    completed_normally = False

    try:
        # Seed the URL into ZAP's session so active scan won't reject with URL_NOT_FOUND.
        if not await zap.access_url(target):
            raise RuntimeError(
                f"target {target} unreachable from ZAP — check connectivity / target is up"
            )

        # Snapshot alerts that exist *before* we start so they don't get mistakenly
        # streamed as fresh findings from this scan (ZAP keeps alerts session-wide
        # across scans). After accessUrl ZAP may add a couple of passive alerts but
        # those are still pre-spider so we still consider them carryover.
        try:
            pre_alerts = await zap.alerts(target)
            pre_existing = {_alert_key(a) for a in pre_alerts}
            logger.info(
                "scan {} pre-existing alerts in ZAP session: {}", scan_id, len(pre_existing)
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("could not snapshot pre-existing alerts: {}", e)
            pre_existing = set()

        spider_id = await zap.spider_start(target)
        await _wait_until(
            lambda: zap.spider_status(spider_id), 100,
            label=f"spider-{spider_id}",
            cancel_event=cancel_event, api=api, scan_id=scan_id,
        )
        if cancel_event.is_set():
            raise asyncio.CancelledError()

        await api.status(scan_id, status="running", progress=30)

        # Start streaming alerts in parallel with the active scan loop. ZAP populates
        # alerts incrementally as plugins fire, so polling /alerts/ is enough.
        stream_task = asyncio.create_task(
            stream_alerts(api, zap, scan_id, target, stream_stop, pre_existing)
        )

        ascan_id = await zap.ascan_start(target)
        # Track consecutive ZAP API failures. A single timeout shouldn't kill the
        # scan — ZAP can momentarily stop responding under heavy plugin load.
        # We log every minute even on success so the operator can see the loop is alive.
        consec_fails = 0
        last_logged_min = -1
        last_p = 0
        while True:
            try:
                p = await zap.ascan_status(ascan_id)
                consec_fails = 0
                last_p = p
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                consec_fails += 1
                logger.warning(
                    "ascan_status failed ({}/{}): {}",
                    consec_fails, ASCAN_MAX_CONSECUTIVE_FAILS, e,
                )
                if consec_fails >= ASCAN_MAX_CONSECUTIVE_FAILS:
                    raise RuntimeError(
                        f"ZAP ascan unresponsive after {consec_fails} retries — last progress {last_p}%"
                    ) from e
                p = last_p  # use stale progress for status update

            try:
                await api.status(scan_id, status="running", progress=30 + int(p * 0.65))
            except Exception:  # noqa: BLE001
                pass  # status push errors shouldn't break the scan loop

            # heartbeat: log once per minute so silent stretches are visible
            cur_min = int((time.monotonic()) // 60)
            if cur_min != last_logged_min:
                logger.info(
                    "ascan-{} progress: {}% (alerts shipped so far via stream task)",
                    ascan_id, p,
                )
                last_logged_min = cur_min

            if p >= 100:
                break
            if not await api.is_active(scan_id):
                cancel_event.set()
                break
            await asyncio.sleep(5)

        # stop streaming, then do a final manual pull to ensure parity with ZAP
        stream_stop.set()
        if stream_task:
            shipped = await stream_task
            stream_task = None
        else:
            shipped = 0

        if cancel_event.is_set():
            # Caller cancelled — don't try to mark completed (state machine rejects),
            # the API already transitioned the scan to CANCELLED.
            logger.info("ZAP scan {} cancelled | partial findings={}", scan_id, shipped)
            return

        await api.status(scan_id, status="completed", progress=100)
        logger.info("ZAP scan {} completed | findings={}", scan_id, shipped)
        completed_normally = True

    except asyncio.CancelledError:
        logger.info("ZAP scan {} cancelled mid-spider", scan_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("ZAP scan {} failed", scan_id)
        await api.status(scan_id, status="failed", error_message=str(e)[:500])
    finally:
        # Cleanup: stop ZAP-side scans so they don't keep crawling after we exit.
        # Critical: do this on FAIL too, not just cancel — otherwise a transient
        # error abandons the active scan and it keeps consuming ZAP CPU/RAM.
        stream_stop.set()
        if stream_task is not None and not stream_task.done():
            try:
                await asyncio.wait_for(stream_task, timeout=10)
            except asyncio.TimeoutError:
                stream_task.cancel()
        if not completed_normally:
            if spider_id:
                await zap.spider_stop(spider_id)
            if ascan_id:
                await zap.ascan_stop(ascan_id)


async def main() -> None:
    rabbitmq_url = os.getenv("COBWEB_RABBITMQ_URL", "amqp://cobweb:cobweb@localhost:5672/")
    api_base = os.getenv("COBWEB_API_BASE", "http://localhost:8000")
    worker_token = os.getenv("COBWEB_WORKER_TOKEN", "dev-worker-token-change-me")
    zap_host = os.getenv("COBWEB_ZAP_HOST", "http://localhost:8090")
    zap_key = os.getenv("COBWEB_ZAP_APIKEY", "")

    api = ApiClient(api_base, worker_token)
    zap = ZapClient(zap_host, zap_key)

    # heartbeat=600 — long ZAP active scans don't cause channel timeouts
    connection = await aio_pika.connect_robust(rabbitmq_url, heartbeat=600)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)
    queue = await channel.declare_queue(QUEUE, durable=True)
    logger.info("ZAP worker ready, waiting on {}", QUEUE)

    async with queue.iterator() as it:
        async for message in it:
            async with message.process(requeue=False):
                try:
                    job = json.loads(message.body)
                except json.JSONDecodeError:
                    logger.error("malformed job payload")
                    continue
                await handle_job(api, zap, job)


if __name__ == "__main__":
    asyncio.run(main())
