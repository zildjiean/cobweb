"""Public API for CI/CD and 3rd-party integrations.

Authentication: X-Api-Key header (org-scoped ApiToken).

Idempotent: if a target with the same base_url already exists in any project of the
org, it's reused. Otherwise the scan is rejected (caller must create + verify a target
through the dashboard first).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.core.deps import get_api_key_principal
from cobweb.db.base import get_db
from cobweb.models.api_token import ApiToken
from cobweb.models.project import Project
from cobweb.models.scan import Scan, ScanProfile, ScanStatus
from cobweb.models.target import Target, TargetStatus
from cobweb.services import scan_orchestrator
from cobweb.services.audit_service import log_event

public_router = APIRouter(prefix="/public/v1", tags=["public"])

THRESHOLD_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


class CiScanRequest(BaseModel):
    target_url: HttpUrl
    profile: str = "quick"
    engine: str = "nuclei"
    threshold: str = "high"  # fail build if any finding ≥ threshold
    wait: bool = True
    wait_timeout_s: int = 600


class CiScanResponse(BaseModel):
    scan_id: str
    status: str
    findings: dict[str, int]
    fail_build: bool
    report_url: str | None = None


def _fail_build(summary: dict[str, int], threshold: str) -> bool:
    cutoff = THRESHOLD_RANK.get(threshold, 3)
    for sev, n in summary.items():
        if n and THRESHOLD_RANK.get(sev, -1) >= cutoff:
            return True
    return False


@public_router.post("/scans", response_model=CiScanResponse)
async def trigger_scan(
    body: CiScanRequest,
    token: ApiToken = Depends(get_api_key_principal),
    db: AsyncSession = Depends(get_db),
):
    # find a verified target with this base_url in the token's org
    base_url = str(body.target_url).rstrip("/")
    stmt = (
        select(Target)
        .join(Project, Project.id == Target.project_id)
        .where(
            Project.org_id == token.org_id,
            Target.base_url.in_([base_url, base_url + "/"]),
            Target.status == TargetStatus.VERIFIED,
        )
        .limit(1)
    )
    target = (await db.execute(stmt)).scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No verified target {base_url!r} in this org. "
            "Add and verify the target via the dashboard first.",
        )

    try:
        scan = await scan_orchestrator.create_scan(
            db,
            org_id=token.org_id,
            project_id=target.project_id,
            target_id=target.id,
            profile=ScanProfile(body.profile),
            triggered_by=None,
            engine=body.engine,
            config={"source": "ci", "token_id": token.id},
        )
    except scan_orchestrator.ScanError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None

    await log_event(
        db, org_id=token.org_id, actor_id=None,
        action="scan.create.public", resource_type="scan", resource_id=scan.id,
        payload={"target_url": base_url, "profile": body.profile, "via_token": token.id},
    )
    await db.commit()

    if not body.wait:
        return CiScanResponse(
            scan_id=scan.id, status=scan.status.value,
            findings={}, fail_build=False, report_url=None,
        )

    deadline = body.wait_timeout_s
    waited = 0.0
    poll = 2.0
    final = scan
    while waited < deadline:
        await asyncio.sleep(poll)
        waited += poll
        final = await db.get(Scan, scan.id)
        await db.refresh(final)
        if final.status in (ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED):
            break

    summary = {k: int(v) for k, v in (final.summary or {}).items()}
    return CiScanResponse(
        scan_id=final.id,
        status=final.status.value,
        findings=summary,
        fail_build=_fail_build(summary, body.threshold)
        if final.status == ScanStatus.COMPLETED
        else final.status != ScanStatus.COMPLETED,
        report_url=None,
    )
