"""/api/v1/scans — scan lifecycle + finding ingestion."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.core.deps import CurrentUser, get_current_user, require_worker_token
from cobweb.core.rbac import require
from cobweb.db.base import get_db
from cobweb.models.project import Project
from cobweb.models.scan import Finding, Scan, ScanProfile, ScanStatus, Severity
from cobweb.schemas.scan import (
    FindingAttackDetails,
    FindingBulkDelete,
    FindingBulkDeleteResponse,
    FindingDetailResponse,
    FindingIngest,
    FindingResponse,
    ScanCreate,
    ScanResponse,
    WorkerStatusUpdate,
)
from cobweb.services import diff_service, notifications, scan_orchestrator, vuln_service
from cobweb.services.audit_service import log_event
from cobweb.services.pubsub import publish_scan_event
from cobweb.services.scan_orchestrator import ScanError, dedupe_hash

router = APIRouter(tags=["scans"])


def _scan_out(s: Scan) -> ScanResponse:
    return ScanResponse(
        id=s.id,
        org_id=s.org_id,
        project_id=s.project_id,
        target_id=s.target_id,
        profile=s.profile.value if hasattr(s.profile, "value") else str(s.profile),
        engine=s.engine,
        status=s.status.value if hasattr(s.status, "value") else str(s.status),
        progress=s.progress,
        template_version=s.template_version,
        started_at=s.started_at.isoformat() if s.started_at else None,
        finished_at=s.finished_at.isoformat() if s.finished_at else None,
        error_message=s.error_message,
        summary=s.summary or {},
        created_at=s.created_at.isoformat(),
    )


def _finding_out(f: Finding) -> FindingResponse:
    return FindingResponse(
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
    )


@router.post("/scans", response_model=ScanResponse, status_code=status.HTTP_201_CREATED)
async def create_scan(
    body: ScanCreate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "scan:create")

    # confirm target belongs to current org via project
    from cobweb.models.target import Target

    target = await db.get(Target, body.target_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target not found")
    project = await db.get(Project, target.project_id)
    if not project or project.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target not found")

    try:
        scan = await scan_orchestrator.create_scan(
            db,
            org_id=current.org_id,
            project_id=project.id,
            target_id=target.id,
            profile=ScanProfile(body.profile),
            triggered_by=current.user.id,
            engine=body.engine,
            config=body.config,
        )
    except ScanError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None

    await log_event(
        db,
        org_id=current.org_id,
        actor_id=current.user.id,
        action="scan.create",
        resource_type="scan",
        resource_id=scan.id,
        payload={"target_id": target.id, "profile": body.profile, "engine": body.engine},
    )
    await db.commit()
    return _scan_out(scan)


@router.get("/scans", response_model=list[ScanResponse])
async def list_scans(
    project_id: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "scan:view")
    scans = await scan_orchestrator.list_scans(
        db, org_id=current.org_id, project_id=project_id, target_id=target_id
    )
    return [_scan_out(s) for s in scans]


@router.get("/scans/{scan_id}", response_model=ScanResponse)
async def get_scan(
    scan_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "scan:view")
    scan = await db.get(Scan, scan_id)
    if not scan or scan.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan not found")
    return _scan_out(scan)


@router.post("/scans/{scan_id}/cancel", response_model=ScanResponse)
async def cancel_scan(
    scan_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "scan:cancel")
    scan = await db.get(Scan, scan_id)
    if not scan or scan.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan not found")
    try:
        scan = await scan_orchestrator.transition(db, scan_id, ScanStatus.CANCELLED)
    except ScanError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    await log_event(
        db, org_id=current.org_id, actor_id=current.user.id,
        action="scan.cancel", resource_type="scan", resource_id=scan.id,
    )
    await db.commit()
    return _scan_out(scan)


@router.delete("/scans/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scan(
    scan_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a scan and its findings. Vulnerabilities (aggregations) survive."""
    require(current.role, "scan:delete")
    scan = await db.get(Scan, scan_id)
    if not scan or scan.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan not found")
    if scan.status in (ScanStatus.QUEUED, ScanStatus.RUNNING):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Cancel the scan before deleting it.",
        )
    target_id = scan.target_id
    profile = scan.profile.value if hasattr(scan.profile, "value") else str(scan.profile)
    await db.delete(scan)
    await log_event(
        db, org_id=current.org_id, actor_id=current.user.id,
        action="scan.delete", resource_type="scan", resource_id=scan_id,
        payload={"target_id": target_id, "profile": profile},
    )
    await db.commit()


@router.get("/scans/{scan_id}/diff")
async def diff_scan(
    scan_id: str,
    base: str | None = Query(default=None, description="Optional base scan id"),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "scan:view")
    scan = await db.get(Scan, scan_id)
    if not scan or scan.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan not found")
    summary = await diff_service.diff_scans(db, scan_id, base)
    return {
        "base_scan_id": summary.base_scan_id,
        "head_scan_id": summary.head_scan_id,
        "new": [e.__dict__ for e in summary.new],
        "fixed": [e.__dict__ for e in summary.fixed],
        "recurring": [e.__dict__ for e in summary.recurring],
        "regression": [e.__dict__ for e in summary.regression],
    }


@router.get("/scans/{scan_id}/findings", response_model=list[FindingResponse])
async def list_findings(
    scan_id: str,
    severity: str | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "vuln:view")
    scan = await db.get(Scan, scan_id)
    if not scan or scan.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan not found")
    stmt = (
        select(Finding)
        .where(Finding.scan_id == scan_id)
        .order_by(Finding.created_at.desc())
    )
    if severity:
        stmt = stmt.where(Finding.severity == Severity(severity))
    result = await db.execute(stmt)
    return [_finding_out(f) for f in result.scalars().all()]


@router.post(
    "/scans/{scan_id}/findings/_delete",
    response_model=FindingBulkDeleteResponse,
)
async def bulk_delete_findings(
    scan_id: str,
    body: FindingBulkDelete,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete one or more findings from a scan and decrement scan.summary counts.

    POST + body (not DELETE) because we need to ship a list of IDs. The endpoint
    accepts 1..500 IDs in a single transaction; mismatched scan_id or org_id IDs
    are rejected up front (404). Vulnerabilities aggregated across other scans
    are not touched.
    """
    require(current.role, "finding:delete")
    scan = await db.get(Scan, scan_id)
    if not scan or scan.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan not found")

    ids = list(dict.fromkeys(body.ids))  # de-dupe but keep order
    result = await db.execute(
        select(Finding).where(
            Finding.id.in_(ids),
            Finding.scan_id == scan_id,
            Finding.org_id == current.org_id,
        )
    )
    findings = list(result.scalars().all())
    if len(findings) != len(ids):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "One or more findings not found in this scan",
        )

    summary = dict(scan.summary or {})
    for f in findings:
        sev = f.severity.value if hasattr(f.severity, "value") else str(f.severity)
        summary[sev] = max(0, int(summary.get(sev, 0)) - 1)
        await db.delete(f)
    scan.summary = summary

    await log_event(
        db, org_id=current.org_id, actor_id=current.user.id,
        action="finding.bulk_delete", resource_type="scan", resource_id=scan_id,
        payload={"count": len(findings), "ids": [f.id for f in findings][:50]},
    )
    await db.commit()
    return FindingBulkDeleteResponse(deleted=len(findings), summary=summary)


_ZAP_RESERVED = {
    "alert", "name", "description", "solution", "reference", "risk",
    "confidence", "method", "param", "attack", "evidence", "inputVector",
    "url", "uri", "tags", "id", "alertRef", "pluginId", "messageId",
    "sourceMessageId", "sourceid", "nodeName", "other", "cweid", "wascid",
}
_NUCLEI_RESERVED = {
    "template-id", "templateID", "info", "matched-at", "host", "matcher-name",
    "request", "response", "type", "ip", "timestamp", "curl-command",
}


def _extract_attack_details(f: Finding) -> FindingAttackDetails | None:
    """Pull forensic fields out of a finding's raw payload — engine-aware."""
    raw = f.raw or {}
    if not raw:
        return None
    # ZAP alert shape: presence of pluginId or alertRef
    if "pluginId" in raw or "alertRef" in raw:
        extras = {k: v for k, v in raw.items() if k not in _ZAP_RESERVED and v not in (None, "", {}, [])}
        return FindingAttackDetails(
            method=raw.get("method") or None,
            parameter=raw.get("param") or None,
            payload=raw.get("attack") or None,
            evidence=raw.get("evidence") or None,
            input_vector=raw.get("inputVector") or None,
            confidence=raw.get("confidence") or None,
            extra=extras,
        )
    # Nuclei shape: has template-id and info dict
    if "template-id" in raw or "templateID" in raw or "info" in raw:
        info = raw.get("info") or {}
        request = raw.get("request") or ""
        method = None
        if isinstance(request, str) and request:
            first_line = request.splitlines()[0] if request else ""
            head = first_line.split(" ", 1)[0]
            if head in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                method = head
        extra: dict[str, Any] = {}
        for key in ("matcher-status", "extracted-results", "type", "ip", "curl-command"):
            v = raw.get(key)
            if v not in (None, "", [], {}):
                extra[key] = v
        if info.get("severity"):
            extra["severity_raw"] = info.get("severity")
        return FindingAttackDetails(
            method=method,
            parameter=raw.get("matcher-name") or None,
            payload=raw.get("matched-line") or info.get("metadata", {}).get("payload") if isinstance(info.get("metadata"), dict) else None,
            evidence=raw.get("matched-line") or None,
            input_vector=raw.get("type") or None,
            confidence=None,
            extra=extra,
        )
    return None


def _finding_detail_out(f: Finding) -> FindingDetailResponse:
    return FindingDetailResponse(
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
        attack_details=_extract_attack_details(f),
    )


@router.get(
    "/scans/{scan_id}/findings/{finding_id}",
    response_model=FindingDetailResponse,
)
async def get_finding(
    scan_id: str,
    finding_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Full finding payload — includes raw request/response from the scanner."""
    require(current.role, "vuln:view")
    f = await db.get(Finding, finding_id)
    if not f or f.scan_id != scan_id or f.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Finding not found")
    return _finding_detail_out(f)


# ── Worker ingestion endpoints (internal, X-Worker-Token auth) ────────


@router.get(
    "/scans/{scan_id}/_worker/active",
    dependencies=[Depends(require_worker_token)],
)
async def worker_probe_active(
    scan_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Probe used by the worker to detect cancellation.

    Returns 200 with `{"active": true}` while the scan is queued/running, or
    410 GONE once the scan has been cancelled or otherwise reached a terminal
    state. The worker terminates the underlying scanner process on 410.
    """
    scan = await db.get(Scan, scan_id)
    if not scan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan not found")
    if scan.status in (ScanStatus.QUEUED, ScanStatus.RUNNING):
        return {"active": True, "status": scan.status.value}
    raise HTTPException(
        status.HTTP_410_GONE,
        f"Scan no longer active (status={scan.status.value})",
    )


@router.post(
    "/scans/{scan_id}/_worker/status",
    response_model=ScanResponse,
    dependencies=[Depends(require_worker_token)],
)
async def worker_update_status(
    scan_id: str,
    body: WorkerStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    scan = await db.get(Scan, scan_id)
    if not scan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan not found")

    target_status = ScanStatus(body.status)
    try:
        scan = await scan_orchestrator.transition(
            db, scan_id, target_status, error=body.error_message
        )
    except ScanError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None

    if body.progress is not None:
        scan.progress = max(0, min(100, body.progress))
    if body.template_version:
        scan.template_version = body.template_version
    await db.commit()

    if target_status == ScanStatus.COMPLETED:
        from cobweb.models.target import Target

        target = await db.get(Target, scan.target_id)
        try:
            await notifications.dispatch_scan_completed(
                db, scan, target.base_url if target else ""
            )
        except Exception:  # noqa: BLE001
            pass  # never fail status update because notifications hiccup

    return _scan_out(scan)


@router.post(
    "/scans/{scan_id}/_worker/findings",
    response_model=list[FindingResponse],
    dependencies=[Depends(require_worker_token)],
)
async def worker_ingest_findings(
    scan_id: str,
    body: list[FindingIngest],
    db: AsyncSession = Depends(get_db),
):
    scan = await db.get(Scan, scan_id)
    if not scan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan not found")

    summary = dict(scan.summary or {})
    inserted: list[Finding] = []
    for item in body:
        h = dedupe_hash(scan.target_id, item.template_id, item.matched_at)
        finding = Finding(
            scan_id=scan_id,
            target_id=scan.target_id,
            org_id=scan.org_id,
            template_id=item.template_id,
            name=item.name,
            severity=Severity(item.severity),
            matched_at=item.matched_at,
            matcher_name=item.matcher_name,
            description=item.description,
            remediation=item.remediation,
            cve=item.cve,
            cwe=item.cwe,
            cvss=item.cvss,
            request=item.request,
            response=item.response,
            raw=item.raw,
            dedupe_hash=h,
        )
        db.add(finding)
        await db.flush()  # need finding.id before vuln upsert
        await vuln_service.upsert_from_finding(db, finding)
        inserted.append(finding)
        summary[item.severity] = int(summary.get(item.severity, 0)) + 1
        await publish_scan_event(
            scan_id,
            {
                "type": "finding",
                "scan_id": scan_id,
                "severity": item.severity,
                "name": item.name,
                "template_id": item.template_id,
            },
        )
    scan.summary = summary
    await db.flush()
    await db.commit()
    return [_finding_out(f) for f in inserted]
