"""/api/v1/suppressions — list + delete auto-FP suppressions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.core.deps import CurrentUser, get_current_user
from cobweb.core.rbac import require
from cobweb.db.base import get_db
from cobweb.models.suppression import FindingSuppression
from cobweb.models.vulnerability import Vulnerability, VulnState
from cobweb.schemas.suppression import SuppressionResponse
from cobweb.services import suppression_service, vuln_service
from cobweb.services.audit_service import log_event

router = APIRouter(tags=["suppressions"])


def _out(s: FindingSuppression) -> SuppressionResponse:
    return SuppressionResponse(
        id=s.id,
        org_id=s.org_id,
        target_id=s.target_id,
        dedupe_hash=s.dedupe_hash,
        reason=s.reason,
        created_by=s.created_by,
        expires_at=s.expires_at.isoformat(),
        created_at=s.created_at.isoformat(),
    )


@router.get("/suppressions", response_model=list[SuppressionResponse])
async def list_suppressions(
    target_id: str | None = Query(default=None),
    include_expired: bool = Query(default=False),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "suppression:view")
    rows = await suppression_service.list_suppressions(
        db,
        org_id=current.org_id,
        target_id=target_id,
        include_expired=include_expired,
    )
    return [_out(s) for s in rows]


@router.delete("/suppressions/{suppression_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_suppression(
    suppression_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a suppression and revive any FALSE_POSITIVE vulns it was suppressing."""
    require(current.role, "suppression:delete")
    s = await db.get(FindingSuppression, suppression_id)
    if not s or s.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Suppression not found")

    target_id = s.target_id
    dedupe_hash = s.dedupe_hash

    await db.delete(s)
    await db.flush()

    # Flip any matching FP vulns back to NEW so the user sees them again.
    res = await db.execute(
        select(Vulnerability).where(
            Vulnerability.target_id == target_id,
            Vulnerability.dedupe_hash == dedupe_hash,
            Vulnerability.state == VulnState.FALSE_POSITIVE,
        )
    )
    revived: list[str] = []
    for v in res.scalars().all():
        try:
            await vuln_service.transition(
                db, v.id, VulnState.NEW, actor_user_id=current.user.id
            )
            revived.append(v.id)
        except vuln_service.VulnError:
            # Race or already-moved vuln; ignore.
            continue

    await log_event(
        db,
        org_id=current.org_id,
        actor_id=current.user.id,
        action="suppression.delete",
        resource_type="suppression",
        resource_id=suppression_id,
        payload={"target_id": target_id, "revived_vuln_ids": revived},
    )
    await db.commit()
    return None
