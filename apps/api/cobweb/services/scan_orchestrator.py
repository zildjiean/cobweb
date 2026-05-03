"""Scan orchestrator: state machine + dispatch to worker queue.

State transitions:
    queued → running → completed | failed | cancelled

Forbidden private/metadata destinations are rejected at scope-validation time.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.core.crypto import decrypt
from cobweb.models.scan import Scan, ScanProfile, ScanStatus
from cobweb.models.target import Target, TargetStatus
from cobweb.services.pubsub import publish_scan_event
from cobweb.services.queue import SCAN_QUEUE_NUCLEI, SCAN_QUEUE_ZAP, get_publisher

BLOCKED_HOSTS = {"localhost", "metadata.google.internal"}
BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


class ScanError(ValueError):
    """Raised on invalid scan input or forbidden state transition."""


def _validate_target_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ScanError("Target URL must be http(s)")
    host = parsed.hostname or ""
    if not host:
        raise ScanError("Target URL has no host")
    if host in BLOCKED_HOSTS:
        raise ScanError(f"Host '{host}' is blocked")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # not a literal IP — DNS hostname is fine
        return
    for net in BLOCKED_NETWORKS:
        if ip in net:
            raise ScanError(f"IP {ip} is in a blocked range")


def dedupe_hash(target_id: str, template_id: str, location: str, param: str = "") -> str:
    blob = f"{target_id}|{template_id}|{location}|{param}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _decrypt_target_auth(target: Target) -> dict | None:
    """Decrypt the target's auth secret (Fernet) and parse the inner JSON.
    Returns None when the target has no auth or the blob is corrupt — corrupt
    blobs log a warning so the scan still runs unauthenticated rather than
    silently failing the dispatch."""
    ct = target.auth_secret_ciphertext
    if not ct:
        return None
    try:
        data = json.loads(decrypt(ct))
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning(
            "target {} auth_secret unreadable, scanning unauthenticated: {}",
            target.id, exc,
        )
        return None
    if not isinstance(data, dict) or data.get("type") not in ("header", "cookie"):
        return None
    return data


async def create_scan(
    db: AsyncSession,
    *,
    org_id: str,
    project_id: str,
    target_id: str,
    profile: ScanProfile,
    triggered_by: str | None,
    engine: str = "nuclei",
    config: dict[str, Any] | None = None,
) -> Scan:
    target = await db.get(Target, target_id)
    if target is None or target.project_id != project_id:
        raise ScanError("Target not found in project")
    if target.status != TargetStatus.VERIFIED:
        raise ScanError("Target ownership not verified")
    _validate_target_url(target.base_url)

    scan = Scan(
        org_id=org_id,
        project_id=project_id,
        target_id=target_id,
        triggered_by=triggered_by,
        profile=profile,
        engine=engine,
        config=config or {},
        status=ScanStatus.QUEUED,
        summary={"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
    )
    db.add(scan)
    await db.flush()

    queue = SCAN_QUEUE_NUCLEI if engine == "nuclei" else SCAN_QUEUE_ZAP
    auth_payload = _decrypt_target_auth(target)
    job = {
        "scan_id": scan.id,
        "target_id": target.id,
        "target_url": target.base_url,
        "scope_includes": target.scope_includes or [],
        "scope_excludes": target.scope_excludes or [],
        "profile": profile.value,
        "engine": engine,
        "org_id": org_id,
        "project_id": project_id,
        "config": config or {},
        "auth": auth_payload,  # None when target has no credentials configured
    }
    publisher = get_publisher()
    await publisher.publish(queue, job)
    await publish_scan_event(scan.id, {"type": "queued", "scan_id": scan.id})
    return scan


async def transition(
    db: AsyncSession, scan_id: str, new_status: ScanStatus, error: str | None = None
) -> Scan:
    scan = await db.get(Scan, scan_id)
    if scan is None:
        raise ScanError("Scan not found")
    valid: dict[ScanStatus, set[ScanStatus]] = {
        ScanStatus.QUEUED: {ScanStatus.RUNNING, ScanStatus.CANCELLED, ScanStatus.FAILED},
        ScanStatus.RUNNING: {ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED},
        ScanStatus.COMPLETED: set(),
        ScanStatus.FAILED: set(),
        ScanStatus.CANCELLED: set(),
    }
    # Same-state is a no-op (worker may report status="running" multiple times for progress)
    if new_status == scan.status:
        return scan
    if new_status not in valid[scan.status]:
        raise ScanError(f"Cannot transition {scan.status.value} → {new_status.value}")
    scan.status = new_status
    now = datetime.now(timezone.utc)
    if new_status == ScanStatus.RUNNING and scan.started_at is None:
        scan.started_at = now
    if new_status in {ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED}:
        scan.finished_at = now
    if error:
        scan.error_message = error
    await publish_scan_event(
        scan.id,
        {"type": "status", "scan_id": scan.id, "status": new_status.value, "error": error},
    )
    return scan


async def update_progress(db: AsyncSession, scan_id: str, progress: int) -> None:
    scan = await db.get(Scan, scan_id)
    if scan is None:
        return
    scan.progress = max(0, min(100, progress))
    await publish_scan_event(
        scan.id, {"type": "progress", "scan_id": scan.id, "progress": scan.progress}
    )


async def list_scans(
    db: AsyncSession,
    org_id: str,
    *,
    project_id: str | None = None,
    target_id: str | None = None,
    limit: int = 100,
) -> list[Scan]:
    stmt = select(Scan).where(Scan.org_id == org_id).order_by(Scan.created_at.desc()).limit(limit)
    if project_id:
        stmt = stmt.where(Scan.project_id == project_id)
    if target_id:
        stmt = stmt.where(Scan.target_id == target_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())
