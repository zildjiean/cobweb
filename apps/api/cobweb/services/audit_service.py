"""Append-only, hash-chained audit log."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.models.audit import AuditLog


def _compute_hash(prev_hash: str | None, payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    h = hashlib.sha256()
    h.update((prev_hash or "").encode())
    h.update(b"|")
    h.update(canonical.encode())
    return h.hexdigest()


async def log_event(
    db: AsyncSession,
    *,
    org_id: str | None,
    actor_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditLog:
    result = await db.execute(select(AuditLog).order_by(desc(AuditLog.id)).limit(1))
    last = result.scalar_one_or_none()
    prev_hash = last.hash if last else None

    body = {
        "org_id": org_id,
        "actor_id": actor_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "payload": payload or {},
    }
    entry = AuditLog(
        org_id=org_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip=ip,
        user_agent=user_agent,
        payload=payload or {},
        prev_hash=prev_hash,
        hash=_compute_hash(prev_hash, body),
    )
    db.add(entry)
    await db.flush()
    return entry
