"""Compare two scans of the same target.

Categorizes findings by dedupe_hash:
    NEW       — present in current, not in previous
    FIXED     — present in previous, not in current
    RECURRING — present in both
    REGRESSION — present in current AND the logical Vuln was previously VERIFIED
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.models.scan import Finding, Scan
from cobweb.models.vulnerability import Vulnerability, VulnState


@dataclass
class DiffEntry:
    dedupe_hash: str
    template_id: str
    name: str
    severity: str
    matched_at: str
    category: str  # new | fixed | recurring | regression


@dataclass
class DiffSummary:
    base_scan_id: str | None
    head_scan_id: str
    new: list[DiffEntry]
    fixed: list[DiffEntry]
    recurring: list[DiffEntry]
    regression: list[DiffEntry]


async def _findings_for_scan(db: AsyncSession, scan_id: str) -> list[Finding]:
    res = await db.execute(select(Finding).where(Finding.scan_id == scan_id))
    return list(res.scalars().all())


async def diff_scans(
    db: AsyncSession, head_scan_id: str, base_scan_id: str | None = None
) -> DiffSummary:
    """Compare head vs base. If base_scan_id is None, picks the most recent
    completed scan for the same target prior to head."""
    head = await db.get(Scan, head_scan_id)
    if head is None:
        raise ValueError("head scan not found")

    if base_scan_id is None:
        stmt = (
            select(Scan)
            .where(
                Scan.target_id == head.target_id,
                Scan.id != head.id,
                Scan.created_at < head.created_at,
            )
            .order_by(Scan.created_at.desc())
            .limit(1)
        )
        prev = (await db.execute(stmt)).scalar_one_or_none()
        base_scan_id = prev.id if prev else None

    head_findings = await _findings_for_scan(db, head_scan_id)
    base_findings = (
        await _findings_for_scan(db, base_scan_id) if base_scan_id else []
    )

    head_map = {f.dedupe_hash: f for f in head_findings}
    base_map = {f.dedupe_hash: f for f in base_findings}

    # Look up vuln states for head's hashes to detect regressions.
    head_hashes = list(head_map.keys())
    vuln_state: dict[str, VulnState] = {}
    if head_hashes:
        res = await db.execute(
            select(Vulnerability.dedupe_hash, Vulnerability.state).where(
                Vulnerability.target_id == head.target_id,
                Vulnerability.dedupe_hash.in_(head_hashes),
            )
        )
        for h, s in res.all():
            vuln_state[h] = s

    def _entry(f: Finding, category: str) -> DiffEntry:
        return DiffEntry(
            dedupe_hash=f.dedupe_hash,
            template_id=f.template_id,
            name=f.name,
            severity=f.severity.value if hasattr(f.severity, "value") else str(f.severity),
            matched_at=f.matched_at,
            category=category,
        )

    new: list[DiffEntry] = []
    recurring: list[DiffEntry] = []
    regression: list[DiffEntry] = []
    for h, f in head_map.items():
        if h in base_map:
            recurring.append(_entry(f, "recurring"))
        else:
            new.append(_entry(f, "new"))
        if vuln_state.get(h) == VulnState.REGRESSION:
            regression.append(_entry(f, "regression"))

    fixed = [
        _entry(f, "fixed") for h, f in base_map.items() if h not in head_map
    ]

    return DiffSummary(
        base_scan_id=base_scan_id,
        head_scan_id=head_scan_id,
        new=new,
        fixed=fixed,
        recurring=recurring,
        regression=regression,
    )
