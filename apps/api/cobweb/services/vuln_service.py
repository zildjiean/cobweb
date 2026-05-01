"""Vulnerability lifecycle service.

Vulnerabilities are logical groupings of Findings. One vuln per (target_id, dedupe_hash).

State machine:
    NEW → TRIAGED → IN_PROGRESS → RESOLVED → VERIFIED
    Any state → FALSE_POSITIVE
    NEW/TRIAGED/IN_PROGRESS → ACCEPTED_RISK
    VERIFIED → REGRESSION (auto, when re-found by a later scan)

SLA windows by severity (config-overridable later):
    critical=7d, high=14d, medium=30d, low=90d, info=None
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.models.scan import Finding
from cobweb.models.target import Target
from cobweb.models.vulnerability import Vulnerability, VulnState

SLA_DAYS: dict[str, int | None] = {
    "critical": 7,
    "high": 14,
    "medium": 30,
    "low": 90,
    "info": None,
}


VALID_TRANSITIONS: dict[VulnState, set[VulnState]] = {
    VulnState.NEW: {VulnState.TRIAGED, VulnState.FALSE_POSITIVE, VulnState.ACCEPTED_RISK},
    VulnState.TRIAGED: {VulnState.IN_PROGRESS, VulnState.FALSE_POSITIVE, VulnState.ACCEPTED_RISK},
    VulnState.IN_PROGRESS: {VulnState.RESOLVED, VulnState.FALSE_POSITIVE, VulnState.ACCEPTED_RISK},
    VulnState.RESOLVED: {VulnState.VERIFIED, VulnState.IN_PROGRESS},
    VulnState.VERIFIED: {VulnState.REGRESSION},
    VulnState.FALSE_POSITIVE: {VulnState.NEW},
    VulnState.ACCEPTED_RISK: {VulnState.NEW},
    VulnState.REGRESSION: {VulnState.IN_PROGRESS, VulnState.FALSE_POSITIVE},
}


class VulnError(ValueError):
    pass


def _sev_str(v: object) -> str:
    return v.value if hasattr(v, "value") else str(v)


def _sla_due(severity: str, base: datetime) -> datetime | None:
    days = SLA_DAYS.get(severity)
    return base + timedelta(days=days) if days is not None else None


async def upsert_from_finding(db: AsyncSession, finding: Finding) -> Vulnerability:
    """Create or update a Vulnerability for a Finding's dedupe_hash."""
    now = datetime.now(timezone.utc)
    sev = _sev_str(finding.severity)

    stmt = select(Vulnerability).where(
        Vulnerability.target_id == finding.target_id,
        Vulnerability.dedupe_hash == finding.dedupe_hash,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()

    if existing is None:
        target = await db.get(Target, finding.target_id)
        if target is None:
            raise VulnError("Target not found")
        vuln = Vulnerability(
            org_id=finding.org_id,
            project_id=target.project_id,
            target_id=finding.target_id,
            dedupe_hash=finding.dedupe_hash,
            template_id=finding.template_id,
            name=finding.name,
            severity=sev,
            state=VulnState.NEW,
            first_seen_scan_id=finding.scan_id,
            last_seen_scan_id=finding.scan_id,
            last_seen_at=now,
            sla_due_at=_sla_due(sev, now),
        )
        db.add(vuln)
        await db.flush()
        return vuln

    existing.last_seen_scan_id = finding.scan_id
    existing.last_seen_at = now
    if existing.state == VulnState.VERIFIED:
        existing.state = VulnState.REGRESSION
    elif existing.state == VulnState.RESOLVED:
        existing.state = VulnState.IN_PROGRESS
    return existing


async def transition(
    db: AsyncSession,
    vuln_id: str,
    new_state: VulnState,
    *,
    notes: str | None = None,
    accepted_until: datetime | None = None,
) -> Vulnerability:
    vuln = await db.get(Vulnerability, vuln_id)
    if vuln is None:
        raise VulnError("Vulnerability not found")
    if new_state not in VALID_TRANSITIONS.get(vuln.state, set()):
        raise VulnError(f"Cannot transition {vuln.state.value} → {new_state.value}")
    vuln.state = new_state
    if notes is not None:
        vuln.notes = notes
    if new_state == VulnState.ACCEPTED_RISK:
        if accepted_until is None:
            raise VulnError("ACCEPTED_RISK requires accepted_until")
        vuln.accepted_until = accepted_until
    return vuln


async def assign(db: AsyncSession, vuln_id: str, user_id: str | None) -> Vulnerability:
    vuln = await db.get(Vulnerability, vuln_id)
    if vuln is None:
        raise VulnError("Vulnerability not found")
    vuln.assigned_to = user_id
    return vuln
