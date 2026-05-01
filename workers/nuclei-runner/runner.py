"""Nuclei worker — consumes scan jobs from RabbitMQ, executes nuclei, streams findings to API.

Required env:
    COBWEB_RABBITMQ_URL     amqp:// URL
    COBWEB_API_BASE         http://api:8000
    COBWEB_WORKER_TOKEN     shared secret matching API setting
    COBWEB_NUCLEI_TEMPLATES optional template dir or pack name

Each message body (JSON):
    {
      "scan_id": "...",
      "target_id": "...",
      "target_url": "https://example.com",
      "scope_includes": [...],
      "scope_excludes": [...],
      "profile": "quick" | "full" | "custom",
      "engine": "nuclei",
      "org_id": "...",
      "project_id": "..."
    }
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import aio_pika
import httpx
from loguru import logger

QUEUE = "cobweb.scans.nuclei"
SEVERITY_MAP = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "info": "info",
    "informational": "info",
    "unknown": "info",
}

# Per-profile rough duration estimate (seconds) — drives the smooth progress curve.
# Real scans land in a wide window so this is just for UX, not accuracy.
PROFILE_ESTIMATE_SEC = {
    "quick": 180,
    "high": 600,
    "full": 1800,
    "custom": 300,
}

# Findings flush cadence
STREAM_FLUSH_INTERVAL_SEC = 2.0
STREAM_FLUSH_BATCH_SIZE = 5
PROGRESS_TICK_SEC = 2.0


def _profile_args(profile: str) -> list[str]:
    """Build the per-profile flag set.

    quick — fast tag-based scan: tech-detect, exposure, misconfig, default-login.
            Shows tech stack + low-hanging fruit, no severity filter so users
            always see at least info-level findings if the target is reachable.
            Typical runtime: 1–3 min.
    high  — `quick` plus CVE templates, filtered to medium/high/critical only.
            Best balance for routine scans. Typical runtime: 5–15 min.
    full  — every template, no filter. Slow but thorough. Typical: 30+ min.
    custom — moderate rate-limit; caller appends -tags / -t etc. via config.
    """
    if profile == "quick":
        return [
            "-tags", "tech,detect,exposure,misconfig,default-login,takeover",
            "-rate-limit", "150",
        ]
    if profile == "high":
        return [
            "-severity", "medium,high,critical",
            "-rate-limit", "150",
        ]
    if profile == "full":
        return ["-rate-limit", "150"]
    return ["-rate-limit", "100"]  # custom


async def spawn_nuclei(
    target: str,
    output_dir: Path,
    profile: str,
    templates: str = "",
    extra_args: list[str] | None = None,
) -> tuple[asyncio.subprocess.Process, Path]:
    """Start nuclei as an async subprocess and return (proc, output_path).

    Caller awaits proc.wait() — leaving us free to run streaming + progress tasks
    in parallel against the JSONL output file.
    """
    out = output_dir / "findings.jsonl"
    cmd = [
        "nuclei",
        "-target", target,
        "-jsonl",
        "-o", str(out),
        "-silent",
        "-timeout", "10",
        *_profile_args(profile),
    ]
    if templates:
        cmd += ["-templates", templates]
    if extra_args:
        cmd += extra_args
    logger.info("running: {}", " ".join(cmd))
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
    except FileNotFoundError:
        logger.error("nuclei binary not found — install nuclei in the worker image")
        raise
    return proc, out


def parse_findings(jsonl_path: Path) -> list[dict[str, Any]]:
    if not jsonl_path.exists():
        return []
    findings: list[dict[str, Any]] = []
    for line in jsonl_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            findings.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("skipping malformed nuclei line")
    return findings


async def stream_findings(
    api: "ApiClient",
    scan_id: str,
    out_path: Path,
    stop_event: asyncio.Event,
) -> set[int]:
    """Tail the nuclei JSONL file while it grows and POST findings as they appear.

    Returns the set of byte offsets already emitted so the final flush can skip them.
    Sends in small chunks (≥STREAM_FLUSH_BATCH_SIZE OR every STREAM_FLUSH_INTERVAL_SEC).
    """
    pos = 0
    pending_raw: list[dict[str, Any]] = []
    last_flush = time.monotonic()
    seen_lines = 0

    async def _flush():
        nonlocal pending_raw, last_flush
        if pending_raw:
            normalized = [normalize(f) for f in pending_raw]
            try:
                await api.findings(scan_id, normalized)
            except Exception as e:  # noqa: BLE001
                logger.warning("stream flush failed: {}", e)
            pending_raw = []
            last_flush = time.monotonic()

    while not stop_event.is_set():
        try:
            if out_path.exists():
                with open(out_path, "rb") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
                if chunk:
                    for raw_line in chunk.split(b"\n"):
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line:
                            continue
                        try:
                            pending_raw.append(json.loads(line))
                            seen_lines += 1
                        except json.JSONDecodeError:
                            continue
            now = time.monotonic()
            if pending_raw and (
                len(pending_raw) >= STREAM_FLUSH_BATCH_SIZE
                or (now - last_flush) >= STREAM_FLUSH_INTERVAL_SEC
            ):
                await _flush()
        except Exception as e:  # noqa: BLE001
            logger.warning("stream loop error: {}", e)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=0.5)
        except asyncio.TimeoutError:
            pass

    # final drain — pick up anything written between last read and process exit
    if out_path.exists():
        with open(out_path, "rb") as f:
            f.seek(pos)
            chunk = f.read()
        for raw_line in chunk.split(b"\n"):
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                pending_raw.append(json.loads(line))
                seen_lines += 1
            except json.JSONDecodeError:
                continue
    await _flush()
    logger.info("scan {} stream done | streamed_lines={}", scan_id, seen_lines)
    return {seen_lines}


async def emit_progress(
    api: "ApiClient",
    scan_id: str,
    profile: str,
    stop_event: asyncio.Event,
    cancel_event: asyncio.Event,
) -> None:
    """Push a smooth progress estimate AND probe for cancel every PROGRESS_TICK_SEC.

    Curve: 5 + (elapsed/estimated)^0.7 * 90, clamped to 5..95.
    Easing exponent 0.7 → progress moves quickly early, slows near the cap so we
    never overshoot if the scan runs longer than the estimate.

    Setting cancel_event tells the orchestrator to terminate the nuclei process.
    Setting stop_event ends this loop normally.
    """
    estimated = PROFILE_ESTIMATE_SEC.get(profile, PROFILE_ESTIMATE_SEC["custom"])
    started = time.monotonic()
    while not stop_event.is_set():
        # Probe cancellation first — if cancelled, skip the progress update so we
        # don't fight with the API's authoritative "cancelled" status.
        active = await api.is_active(scan_id)
        if not active:
            logger.info("scan {} cancelled by user — signalling terminate", scan_id)
            cancel_event.set()
            stop_event.set()
            break
        elapsed = time.monotonic() - started
        ratio = min(elapsed / estimated, 1.0)
        progress = int(min(95, max(5, 5 + (ratio ** 0.7) * 90)))
        try:
            await api.status(scan_id, status="running", progress=progress)
        except Exception as e:  # noqa: BLE001
            logger.warning("progress update failed: {}", e)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=PROGRESS_TICK_SEC)
        except asyncio.TimeoutError:
            pass


def _scrub(value: Any) -> Any:
    """Recursively strip null bytes (\\x00) from strings — Postgres TEXT rejects them."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def normalize(finding: dict[str, Any]) -> dict[str, Any]:
    finding = _scrub(finding)
    info = finding.get("info") or {}
    classification = info.get("classification") or {}
    severity_raw = (info.get("severity") or "info").lower()
    return {
        "template_id": finding.get("template-id") or finding.get("templateID") or "unknown",
        "name": info.get("name") or finding.get("template-id") or "unknown",
        "severity": SEVERITY_MAP.get(severity_raw, "info"),
        "matched_at": finding.get("matched-at") or finding.get("host") or "",
        "matcher_name": finding.get("matcher-name"),
        "description": info.get("description"),
        "remediation": info.get("remediation"),
        "cve": (classification.get("cve-id") or [None])[0]
        if isinstance(classification.get("cve-id"), list)
        else classification.get("cve-id"),
        "cwe": (classification.get("cwe-id") or [None])[0]
        if isinstance(classification.get("cwe-id"), list)
        else classification.get("cwe-id"),
        "cvss": str(classification.get("cvss-score")) if classification.get("cvss-score") else None,
        "request": finding.get("request"),
        "response": finding.get("response"),
        "raw": finding,
    }


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
        # ship in chunks of 50
        for i in range(0, len(items), 50):
            chunk = items[i : i + 50]
            async with httpx.AsyncClient(timeout=30.0) as c:
                r = await c.post(url, headers=self._headers, json=chunk)
                if r.status_code >= 300:
                    logger.warning("ingest failed: {} {}", r.status_code, r.text)

    async def is_active(self, scan_id: str) -> bool:
        """Probe whether the scan is still active. 410 GONE → cancelled/terminal."""
        url = f"{self._base}/api/v1/scans/{scan_id}/_worker/active"
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(url, headers=self._headers)
            if r.status_code == 200:
                return True
            if r.status_code == 410:
                return False
            logger.warning("active probe odd status {} {}", r.status_code, r.text)
            return True  # fail-open: don't kill the scan on transient errors
        except Exception as e:  # noqa: BLE001
            logger.warning("active probe error: {}", e)
            return True


async def handle_job(api: ApiClient, job: dict[str, Any]) -> None:
    scan_id = job["scan_id"]
    target = job["target_url"]
    profile = job.get("profile", "quick")
    logger.info("scan {} starting | target={} profile={}", scan_id, target, profile)
    await api.status(
        scan_id,
        status="running",
        progress=5,
        template_version=os.getenv("COBWEB_TEMPLATE_VERSION"),
    )

    config = job.get("config") or {}
    extra: list[str] = []
    if isinstance(config.get("tags"), str) and config["tags"]:
        extra += ["-tags", config["tags"]]
    if isinstance(config.get("nuclei_args"), list):
        extra += [str(a) for a in config["nuclei_args"]]

    try:
        with tempfile.TemporaryDirectory() as tmp:
            proc, out = await spawn_nuclei(
                target, Path(tmp), profile,
                os.getenv("COBWEB_NUCLEI_TEMPLATES", ""),
                extra_args=extra,
            )
            stop = asyncio.Event()
            cancel = asyncio.Event()
            stream_task = asyncio.create_task(stream_findings(api, scan_id, out, stop))
            progress_task = asyncio.create_task(
                emit_progress(api, scan_id, profile, stop, cancel)
            )

            # Race: nuclei finishing OR a cancel signal from the API probe.
            proc_task = asyncio.create_task(proc.wait())
            cancel_wait = asyncio.create_task(cancel.wait())
            done, _ = await asyncio.wait(
                {proc_task, cancel_wait},
                timeout=3600,
                return_when=asyncio.FIRST_COMPLETED,
            )

            cancelled = cancel.is_set()
            if cancelled:
                # User cancelled — terminate nuclei, then drain its exit
                logger.info("scan {} terminating nuclei after cancel", scan_id)
                if proc.returncode is None:
                    proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        proc.kill()
                        await proc.wait()
            elif proc_task not in done:
                # Timeout (3600s) — kill and surface as failure
                proc.terminate()
                await proc.wait()
                raise asyncio.TimeoutError("nuclei timeout (1h)")

            stop.set()
            await asyncio.gather(stream_task, progress_task, return_exceptions=True)
            cancel_wait.cancel()
            total = len(parse_findings(out))

        if cancelled:
            # API already transitioned scan → CANCELLED when the user clicked
            # Stop. Don't post a status here or we'd race the state machine.
            logger.info("scan {} cancelled | partial findings={}", scan_id, total)
        else:
            await api.status(scan_id, status="completed", progress=100)
            logger.info("scan {} completed | findings={}", scan_id, total)
    except Exception as e:  # noqa: BLE001
        logger.exception("scan {} failed", scan_id)
        await api.status(scan_id, status="failed", error_message=str(e)[:500])


async def main() -> None:
    rabbitmq_url = os.getenv("COBWEB_RABBITMQ_URL", "amqp://cobweb:cobweb@localhost:5672/")
    api_base = os.getenv("COBWEB_API_BASE", "http://localhost:8000")
    worker_token = os.getenv("COBWEB_WORKER_TOKEN", "dev-worker-token-change-me")

    api = ApiClient(api_base, worker_token)
    # heartbeat=600 protects against long-running scans where nothing else flows on the channel
    connection = await aio_pika.connect_robust(rabbitmq_url, heartbeat=600)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)
    queue = await channel.declare_queue(QUEUE, durable=True)
    logger.info("nuclei worker ready, waiting on {}", QUEUE)

    async with queue.iterator() as iterator:
        async for message in iterator:
            async with message.process(requeue=False):
                try:
                    job = json.loads(message.body)
                except json.JSONDecodeError:
                    logger.error("malformed job payload, dropping")
                    continue
                await handle_job(api, job)


if __name__ == "__main__":
    asyncio.run(main())
