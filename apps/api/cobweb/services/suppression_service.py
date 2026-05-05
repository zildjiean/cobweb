"""FindingSuppression service.

Auto-suppression of repeat findings on the same (target, dedupe_hash) after
a user marks a Vulnerability as FALSE_POSITIVE.

Lifecycle:
    transition vuln -> FALSE_POSITIVE  : upsert_suppression()
    transition vuln FALSE_POSITIVE -> NEW : remove_suppression()
    finding ingested : if is_suppressed() -> new vuln auto-lands in FALSE_POSITIVE
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.models.suppression import FindingSuppression

DEFAULT_TTL_DAYS = 90


async def upsert_suppression(
    db: AsyncSession,
    *,
    org_id: str,
    target_id: str,
    dedupe_hash: str,
    created_by: str | None,
    reason: str | None = None,
    ttl_days: int = DEFAULT_TTL_DAYS,
) -> FindingSuppression:
    """Create or refresh a suppression. Resets expires_at to now + ttl_days."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)
    stmt = select(FindingSuppression).where(
        FindingSuppression.target_id == target_id,
        FindingSuppression.dedupe_hash == dedupe_hash,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        existing.expires_at = expires_at
        if reason is not None:
            existing.reason = reason
        if created_by is not None:
            existing.created_by = created_by
        return existing
    sup = FindingSuppression(
        org_id=org_id,
        target_id=target_id,
        dedupe_hash=dedupe_hash,
        reason=reason,
        created_by=created_by,
        expires_at=expires_at,
    )
    db.add(sup)
    await db.flush()
    return sup


async def remove_suppression(
    db: AsyncSession, *, target_id: str, dedupe_hash: str
) -> int:
    """Delete the suppression for (target, dedupe_hash) if it exists. Returns row count."""
    res = await db.execute(
        delete(FindingSuppression).where(
            FindingSuppression.target_id == target_id,
            FindingSuppression.dedupe_hash == dedupe_hash,
        )
    )
    return res.rowcount or 0


async def is_suppressed(
    db: AsyncSession, *, target_id: str, dedupe_hash: str
) -> bool:
    """Return True if an active (non-expired) suppression exists."""
    now = datetime.now(timezone.utc)
    stmt = select(FindingSuppression.id).where(
        FindingSuppression.target_id == target_id,
        FindingSuppression.dedupe_hash == dedupe_hash,
        FindingSuppression.expires_at > now,
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def list_suppressions(
    db: AsyncSession,
    *,
    org_id: str,
    target_id: str | None = None,
    include_expired: bool = False,
) -> list[FindingSuppression]:
    stmt = (
        select(FindingSuppression)
        .where(FindingSuppression.org_id == org_id)
        .order_by(FindingSuppression.created_at.desc())
        .limit(500)
    )
    if target_id is not None:
        stmt = stmt.where(FindingSuppression.target_id == target_id)
    if not include_expired:
        stmt = stmt.where(FindingSuppression.expires_at > datetime.now(timezone.utc))
    return list((await db.execute(stmt)).scalars().all())
