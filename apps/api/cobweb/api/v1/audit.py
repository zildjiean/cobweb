"""/api/v1/audit-logs — read-only audit log timeline (admin/auditor)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.core.deps import CurrentUser, get_current_user
from cobweb.core.rbac import require
from cobweb.db.base import get_db
from cobweb.models.audit import AuditLog

router = APIRouter(tags=["audit"])


@router.get("/audit-logs")
async def list_audit_logs(
    limit: int = Query(default=200, le=1000),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "audit:view")
    stmt = (
        select(AuditLog)
        .where(AuditLog.org_id == current.org_id)
        .order_by(AuditLog.id.desc())
        .limit(limit)
    )
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    res = await db.execute(stmt)
    return [
        {
            "id": e.id,
            "actor_id": e.actor_id,
            "action": e.action,
            "resource_type": e.resource_type,
            "resource_id": e.resource_id,
            "ip": e.ip,
            "user_agent": e.user_agent,
            "payload": e.payload,
            "hash": e.hash,
            "prev_hash": e.prev_hash,
            "created_at": e.created_at.isoformat(),
        }
        for e in res.scalars().all()
    ]
