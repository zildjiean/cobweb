"""/api/v1/scans/{id}/report — generate HTML/PDF report."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.core.deps import CurrentUser, get_current_user_browser
from cobweb.core.rbac import require
from cobweb.db.base import get_db
from cobweb.models.scan import Scan
from cobweb.services import report_service
from cobweb.services.audit_service import log_event

router = APIRouter(tags=["reports"])

_KINDS = {"executive", "technical", "owasp", "pci_dss", "iso27001"}


@router.get("/scans/{scan_id}/report")
async def get_scan_report(
    scan_id: str,
    kind: str = Query(default="technical"),
    fmt: str = Query(default="html", pattern="^(html|pdf)$"),
    current: CurrentUser = Depends(get_current_user_browser),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "scan:view")
    scan = await db.get(Scan, scan_id)
    if not scan or scan.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan not found")
    if kind not in _KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown report kind: {kind}")

    if fmt == "pdf":
        try:
            pdf = await report_service.render_pdf(db, scan_id, kind)
        except RuntimeError as e:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from None
        await log_event(
            db, org_id=current.org_id, actor_id=current.user.id,
            action="report.export", resource_type="scan", resource_id=scan_id,
            payload={"kind": kind, "fmt": "pdf"},
        )
        await db.commit()
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="cobweb-{scan_id[:8]}-{kind}.pdf"',
            },
        )

    html = await report_service.render_html(db, scan_id, kind)
    return HTMLResponse(content=html)
