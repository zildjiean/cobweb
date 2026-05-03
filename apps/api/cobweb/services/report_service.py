"""Report generation — HTML via Jinja2, PDF via WeasyPrint.

Five report kinds with genuinely different content:
  - executive: 1-page leadership summary (headline metrics, top findings, no full table)
  - technical: per-finding detail (description, remediation, CVE/CWE/CVSS, payloads)
  - owasp: findings grouped by OWASP Top 10 category
  - pci_dss: findings grouped by PCI-DSS Requirement 6.5
  - iso27001: findings grouped by ISO 27001 Annex A control

WeasyPrint requires Pango/Cairo system libs. If they aren't available,
HTML rendering still works.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.models.org import Organization
from cobweb.models.scan import Finding, Scan
from cobweb.models.target import Target
from cobweb.services.report_templates import compliance_map

TEMPLATE_DIR = Path(__file__).parent / "report_templates"

REPORT_TITLES = {
    "executive": "Executive Security Report",
    "technical": "Technical Vulnerability Report",
    "owasp": "OWASP Top 10 Compliance Report",
    "pci_dss": "PCI-DSS Requirement 6.5 Report",
    "iso27001": "ISO 27001 Annex A Report",
}

REPORT_SUBTITLES = {
    "executive": "Leadership briefing — key risks at a glance",
    "technical": "Per-finding analysis with payloads and remediation",
    "owasp": "Findings mapped to OWASP Top 10 (2021)",
    "pci_dss": "Findings mapped to PCI-DSS Requirement 6.5",
    "iso27001": "Findings mapped to ISO 27001:2022 Annex A controls",
}

SEV_ORDER = ("critical", "high", "medium", "low", "info")

# Print-friendly severity colors (hex). Match the on-screen palette tonally
# but pick darker shades that meet WCAG contrast on white paper.
SEV_COLORS = {
    "critical": "#c01515",
    "high": "#d96118",
    "medium": "#c08a0a",
    "low": "#2c8a3a",
    "info": "#5a6678",
}

# Severity weights for risk score. Higher weight ⇒ more impact on score.
_RISK_WEIGHT = {"critical": 10, "high": 5, "medium": 2, "low": 0.5, "info": 0}


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )


def _sev_value(f: Finding) -> str:
    return f.severity.value if hasattr(f.severity, "value") else str(f.severity)


def _enum_value(v) -> str:
    return v.value if hasattr(v, "value") else str(v)


async def _gather(
    db: AsyncSession, scan_id: str
) -> tuple[Scan, Target, Organization | None, list[Finding]]:
    scan = await db.get(Scan, scan_id)
    if scan is None:
        raise ValueError("Scan not found")
    target = await db.get(Target, scan.target_id)
    if target is None:
        raise ValueError("Target not found")
    org = await db.get(Organization, scan.org_id)
    res = await db.execute(select(Finding).where(Finding.scan_id == scan_id))
    findings = list(res.scalars().all())
    return scan, target, org, findings


def _serialize_finding(f: Finding) -> dict:
    return {
        "severity": _sev_value(f),
        "template_id": f.template_id,
        "name": f.name,
        "matched_at": f.matched_at,
        "matcher_name": f.matcher_name,
        "description": f.description,
        "remediation": f.remediation,
        "cve": f.cve,
        "cwe": f.cwe,
        "cvss": f.cvss,
    }


def _summary_counts(findings: list[Finding]) -> dict[str, int]:
    counts = dict.fromkeys(SEV_ORDER, 0)
    for f in findings:
        sev = _sev_value(f)
        if sev in counts:
            counts[sev] += 1
    return counts


def _risk_score(counts: dict[str, int]) -> int:
    """0–100, where 100 = clean. Capped at 0 for very-bad-state."""
    raw = sum(counts.get(s, 0) * _RISK_WEIGHT[s] for s in SEV_ORDER)
    return max(0, min(100, round(100 - raw)))


def _risk_grade(score: int) -> tuple[str, str]:
    """(letter, color) — color is print-friendly hex."""
    if score >= 90:
        return "A", "#1f8c3b"
    if score >= 80:
        return "B", "#3aa455"
    if score >= 70:
        return "C", "#c08a0a"
    if score >= 60:
        return "D", "#d96118"
    return "F", "#c01515"


def _donut_segments(counts: dict[str, int]) -> list[dict]:
    """SVG-ready segments: each {color, label, count, pct, dasharray, offset}.
    Circumference = 100 (we use stroke-dasharray with `pathLength=100`)."""
    total = sum(counts.values()) or 1
    segments = []
    cursor = 0.0
    for sev in SEV_ORDER:
        n = counts[sev]
        if n == 0:
            continue
        pct = n / total * 100
        segments.append(
            {
                "color": SEV_COLORS[sev],
                "label": sev,
                "count": n,
                "pct": round(pct, 1),
                "dasharray": f"{pct:.3f} {100 - pct:.3f}",
                "offset": f"{(-cursor) % 100:.3f}",
            }
        )
        cursor += pct
    return segments


def _group_by_owasp(findings: list[Finding]) -> list[dict]:
    """Returns ordered groups [{id, label, findings: [...]}, ...] including 'Unmapped'."""
    buckets: dict[str, list[Finding]] = defaultdict(list)
    labels: dict[str, str] = {}
    for f in findings:
        cat = compliance_map.owasp_category(f.template_id)
        if cat:
            buckets[cat[0]].append(f)
            labels[cat[0]] = cat[1]
        else:
            buckets["unmapped"].append(f)
            labels["unmapped"] = "Unmapped"
    # Order by canonical OWASP id, then unmapped last
    ordered_ids = [oid for oid in compliance_map.OWASP_TOP_10 if oid in buckets]
    if "unmapped" in buckets:
        ordered_ids.append("unmapped")
    return [
        {
            "id": oid,
            "label": labels[oid],
            "findings": [_serialize_finding(f) for f in _sort_findings(buckets[oid])],
        }
        for oid in ordered_ids
    ]


def _group_by_pci(findings: list[Finding]) -> list[dict]:
    buckets: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        reqs = compliance_map.pci_dss(f.template_id)
        if reqs:
            for req, _ in reqs:
                buckets[req].append(f)
        else:
            buckets["unmapped"].append(f)
    labels = {**compliance_map.PCI_DSS_6_5, "unmapped": "Unmapped to PCI-DSS"}
    ordered = [r for r in compliance_map.PCI_DSS_6_5 if r in buckets]
    if "unmapped" in buckets:
        ordered.append("unmapped")
    return [
        {
            "id": req,
            "label": labels[req],
            "findings": [_serialize_finding(f) for f in _sort_findings(buckets[req])],
        }
        for req in ordered
    ]


def _group_by_iso(findings: list[Finding]) -> list[dict]:
    buckets: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        controls = compliance_map.iso_27001(f.template_id)
        if controls:
            for ctrl, _ in controls:
                buckets[ctrl].append(f)
        else:
            buckets["unmapped"].append(f)
    labels = {**compliance_map.ISO_27001_CONTROLS, "unmapped": "Unmapped to ISO 27001"}
    ordered = [c for c in compliance_map.ISO_27001_CONTROLS if c in buckets]
    if "unmapped" in buckets:
        ordered.append("unmapped")
    return [
        {
            "id": ctrl,
            "label": labels[ctrl],
            "findings": [_serialize_finding(f) for f in _sort_findings(buckets[ctrl])],
        }
        for ctrl in ordered
    ]


def _sort_findings(findings: list[Finding]) -> list[Finding]:
    """Severity-desc, then name."""
    order = {s: i for i, s in enumerate(SEV_ORDER)}
    return sorted(findings, key=lambda f: (order.get(_sev_value(f), 99), f.name or ""))


async def render_html(db: AsyncSession, scan_id: str, kind: str = "technical") -> str:
    scan, target, org, findings = await _gather(db, scan_id)
    counts = _summary_counts(findings)
    score = _risk_score(counts)
    grade, grade_color = _risk_grade(score)
    sorted_findings = _sort_findings(findings)
    serialized = [_serialize_finding(f) for f in sorted_findings]

    # Per-kind groupings (only the relevant one is computed; others are empty
    # to keep the template branches simple).
    owasp_groups = _group_by_owasp(findings) if kind == "owasp" else []
    pci_groups = _group_by_pci(findings) if kind == "pci_dss" else []
    iso_groups = _group_by_iso(findings) if kind == "iso27001" else []

    # Executive: top 5 most severe findings
    top_findings = serialized[:5] if kind == "executive" else []

    env = _env()
    template = env.get_template("report.html.j2")
    return template.render(
        kind=kind,
        report_title=REPORT_TITLES.get(kind, REPORT_TITLES["technical"]),
        report_subtitle=REPORT_SUBTITLES.get(kind, ""),
        org={"name": org.name if org else "—"},
        scan={
            "id": scan.id,
            "engine": scan.engine,
            "profile": _enum_value(scan.profile),
            "status": _enum_value(scan.status),
            "started_at": scan.started_at,
            "finished_at": scan.finished_at,
        },
        target={"base_url": target.base_url, "name": target.name},
        findings=serialized,
        top_findings=top_findings,
        summary=counts,
        total_findings=len(findings),
        risk_score=score,
        risk_grade=grade,
        risk_grade_color=grade_color,
        donut=_donut_segments(counts),
        sev_colors=SEV_COLORS,
        sev_order=list(SEV_ORDER),
        owasp_groups=owasp_groups,
        pci_groups=pci_groups,
        iso_groups=iso_groups,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


async def render_pdf(db: AsyncSession, scan_id: str, kind: str = "technical") -> bytes:
    html = await render_html(db, scan_id, kind)
    try:
        from weasyprint import HTML  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "WeasyPrint not installed; install system libs (libcairo2, libpango-1.0-0, "
            "libpangoft2-1.0-0) and `pip install weasyprint`."
        ) from e
    return HTML(string=html).write_pdf()
