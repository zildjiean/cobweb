"""/api/v1/vulnerabilities — vuln list + lifecycle transitions."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.core.deps import CurrentUser, get_current_user
from cobweb.core.rbac import require
from cobweb.db.base import get_db
from cobweb.models.scan import Finding
from cobweb.models.vulnerability import Vulnerability, VulnState
from cobweb.schemas.scan import FindingDetailResponse
from cobweb.schemas.vulnerability import VulnAssign, VulnResponse, VulnTransition
from cobweb.services import vuln_service
from cobweb.services.audit_service import log_event
from cobweb.services.vuln_service import VulnError

router = APIRouter(tags=["vulnerabilities"])


def _vuln_out(v: Vulnerability) -> VulnResponse:
    return VulnResponse(
        id=v.id,
        org_id=v.org_id,
        project_id=v.project_id,
        target_id=v.target_id,
        dedupe_hash=v.dedupe_hash,
        template_id=v.template_id,
        name=v.name,
        severity=v.severity,
        state=v.state.value if hasattr(v.state, "value") else str(v.state),
        first_seen_scan_id=v.first_seen_scan_id,
        last_seen_scan_id=v.last_seen_scan_id,
        last_seen_at=v.last_seen_at.isoformat() if v.last_seen_at else None,
        assigned_to=v.assigned_to,
        sla_due_at=v.sla_due_at.isoformat() if v.sla_due_at else None,
        accepted_until=v.accepted_until.isoformat() if v.accepted_until else None,
        notes=v.notes,
        created_at=v.created_at.isoformat(),
    )


@router.get("/vulnerabilities", response_model=list[VulnResponse])
async def list_vulns(
    project_id: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    state: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "vuln:view")
    stmt = (
        select(Vulnerability)
        .where(Vulnerability.org_id == current.org_id)
        .order_by(Vulnerability.created_at.desc())
        .limit(500)
    )
    if project_id:
        stmt = stmt.where(Vulnerability.project_id == project_id)
    if target_id:
        stmt = stmt.where(Vulnerability.target_id == target_id)
    if state:
        stmt = stmt.where(Vulnerability.state == VulnState(state))
    if severity:
        stmt = stmt.where(Vulnerability.severity == severity)
    result = await db.execute(stmt)
    return [_vuln_out(v) for v in result.scalars().all()]


@router.get("/vulnerabilities/{vuln_id}", response_model=VulnResponse)
async def get_vuln(
    vuln_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "vuln:view")
    v = await db.get(Vulnerability, vuln_id)
    if not v or v.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vulnerability not found")
    return _vuln_out(v)


@router.post("/vulnerabilities/{vuln_id}/transition", response_model=VulnResponse)
async def transition_vuln(
    vuln_id: str,
    body: VulnTransition,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "vuln:update")
    v = await db.get(Vulnerability, vuln_id)
    if not v or v.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vulnerability not found")
    accepted_until = (
        datetime.fromisoformat(body.accepted_until.replace("Z", "+00:00"))
        if body.accepted_until
        else None
    )
    try:
        v = await vuln_service.transition(
            db, vuln_id, VulnState(body.state),
            notes=body.notes, accepted_until=accepted_until,
        )
    except VulnError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    await log_event(
        db, org_id=current.org_id, actor_id=current.user.id,
        action=f"vuln.transition.{body.state}", resource_type="vulnerability",
        resource_id=v.id, payload={"notes": body.notes},
    )
    await db.commit()
    return _vuln_out(v)


@router.get(
    "/vulnerabilities/{vuln_id}/findings",
    response_model=list[FindingDetailResponse],
)
async def list_vuln_findings(
    vuln_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Findings (per-scan instances) tied to this logical vuln, latest first."""
    require(current.role, "vuln:view")
    v = await db.get(Vulnerability, vuln_id)
    if not v or v.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vulnerability not found")
    res = await db.execute(
        select(Finding)
        .where(Finding.target_id == v.target_id, Finding.dedupe_hash == v.dedupe_hash)
        .order_by(Finding.created_at.desc())
    )
    out: list[FindingDetailResponse] = []
    for f in res.scalars().all():
        out.append(
            FindingDetailResponse(
                id=f.id,
                scan_id=f.scan_id,
                target_id=f.target_id,
                template_id=f.template_id,
                name=f.name,
                severity=f.severity.value if hasattr(f.severity, "value") else str(f.severity),
                matched_at=f.matched_at,
                description=f.description,
                remediation=f.remediation,
                cve=f.cve,
                cwe=f.cwe,
                dedupe_hash=f.dedupe_hash,
                created_at=f.created_at.isoformat(),
                matcher_name=f.matcher_name,
                cvss=f.cvss,
                request=f.request,
                response=f.response,
                raw=f.raw or {},
            )
        )
    return out


@router.post("/vulnerabilities/{vuln_id}/assign", response_model=VulnResponse)
async def assign_vuln(
    vuln_id: str,
    body: VulnAssign,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "vuln:update")
    v = await db.get(Vulnerability, vuln_id)
    if not v or v.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vulnerability not found")
    v = await vuln_service.assign(db, vuln_id, body.user_id)
    await log_event(
        db, org_id=current.org_id, actor_id=current.user.id,
        action="vuln.assign", resource_type="vulnerability", resource_id=v.id,
        payload={"assigned_to": body.user_id},
    )
    await db.commit()
    return _vuln_out(v)
