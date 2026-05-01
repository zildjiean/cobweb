"""/api/v1/notification-rules — CRUD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.core.deps import CurrentUser, get_current_user
from cobweb.core.rbac import require
from cobweb.db.base import get_db
from cobweb.models.notification import NotificationChannel, NotificationRule
from cobweb.services.audit_service import log_event

router = APIRouter(tags=["notifications"])


class RuleCreate(BaseModel):
    channel: str
    target: str
    project_id: str | None = None
    severity_threshold: str = "medium"
    enabled: bool = True
    config: dict = {}


class RuleResponse(BaseModel):
    id: str
    channel: str
    target: str
    project_id: str | None
    severity_threshold: str
    enabled: bool
    created_at: str


def _out(r: NotificationRule) -> RuleResponse:
    return RuleResponse(
        id=r.id,
        channel=r.channel.value if hasattr(r.channel, "value") else str(r.channel),
        target=r.target,
        project_id=r.project_id,
        severity_threshold=r.severity_threshold,
        enabled=r.enabled,
        created_at=r.created_at.isoformat(),
    )


@router.get("/notification-rules", response_model=list[RuleResponse])
async def list_rules(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "integration:manage")
    res = await db.execute(
        select(NotificationRule).where(NotificationRule.org_id == current.org_id)
    )
    return [_out(r) for r in res.scalars().all()]


@router.post(
    "/notification-rules", response_model=RuleResponse, status_code=status.HTTP_201_CREATED
)
async def create_rule(
    body: RuleCreate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "integration:manage")
    rule = NotificationRule(
        org_id=current.org_id,
        project_id=body.project_id,
        channel=NotificationChannel(body.channel),
        target=body.target,
        severity_threshold=body.severity_threshold,
        enabled=body.enabled,
        config=body.config,
    )
    db.add(rule)
    await db.flush()
    await log_event(
        db, org_id=current.org_id, actor_id=current.user.id,
        action="notification.create", resource_type="notification_rule",
        resource_id=rule.id, payload={"channel": body.channel, "target": body.target},
    )
    await db.commit()
    return _out(rule)


@router.delete("/notification-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "integration:manage")
    rule = await db.get(NotificationRule, rule_id)
    if not rule or rule.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    await db.delete(rule)
    await log_event(
        db, org_id=current.org_id, actor_id=current.user.id,
        action="notification.delete", resource_type="notification_rule",
        resource_id=rule_id,
    )
    await db.commit()
