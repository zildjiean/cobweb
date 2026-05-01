"""Report generation — HTML via Jinja2, PDF via WeasyPrint.

WeasyPrint requires Pango/Cairo system libs. If they aren't available,
HTML rendering still works.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )


async def _gather(db: AsyncSession, scan_id: str) -> tuple[Scan, Target, list[Finding]]:
    scan = await db.get(Scan, scan_id)
    if scan is None:
        raise ValueError("Scan not found")
    target = await db.get(Target, scan.target_id)
    if target is None:
        raise ValueError("Target not found")
    res = await db.execute(select(Finding).where(Finding.scan_id == scan_id))
    findings = list(res.scalars().all())
    return scan, target, findings


def _build_compliance(findings: list[Finding]) -> list[dict]:
    rows: list[dict] = []
    for f in findings:
        rows.append(
            {
                "name": f.name,
                "owasp": compliance_map.owasp_category(f.template_id),
                "pci": compliance_map.pci_dss(f.template_id),
                "iso": compliance_map.iso_27001(f.template_id),
            }
        )
    return rows


async def render_html(db: AsyncSession, scan_id: str, kind: str = "technical") -> str:
    scan, target, findings = await _gather(db, scan_id)
    env = _env()
    template = env.get_template("report.html.j2")
    return template.render(
        report_title=REPORT_TITLES.get(kind, REPORT_TITLES["technical"]),
        scan={
            "id": scan.id,
            "engine": scan.engine,
            "profile": scan.profile.value if hasattr(scan.profile, "value") else str(scan.profile),
            "status": scan.status.value if hasattr(scan.status, "value") else str(scan.status),
        },
        target={"base_url": target.base_url, "name": target.name},
        findings=[
            {
                "severity": f.severity.value if hasattr(f.severity, "value") else str(f.severity),
                "template_id": f.template_id,
                "name": f.name,
                "matched_at": f.matched_at,
            }
            for f in sorted(
                findings,
                key=lambda f: ["critical", "high", "medium", "low", "info"].index(
                    f.severity.value if hasattr(f.severity, "value") else str(f.severity)
                ),
            )
        ],
        summary={k: int(v) for k, v in (scan.summary or {}).items()},
        compliance=_build_compliance(findings) if kind in ("owasp", "pci_dss", "iso27001", "technical") else [],
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
