"""WebSocket endpoint for live scan progress.

Client subscribes to `/api/v1/ws/scans/{scan_id}?token=<jwt>`. Authenticates the
JWT, verifies org membership for the scan, then forwards Redis pub/sub events.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from cobweb.core.security import decode_token
from cobweb.db.base import get_sessionmaker
from cobweb.models.org import OrgMember
from cobweb.models.scan import Scan
from cobweb.services.pubsub import subscribe_scan

router = APIRouter()


@router.websocket("/ws/scans/{scan_id}")
async def scan_ws(websocket: WebSocket, scan_id: str, token: str | None = None) -> None:
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        payload = decode_token(token)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    if payload.get("type") != "access":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    session_factory = get_sessionmaker()
    async with session_factory() as db:
        scan = await db.get(Scan, scan_id)
        if not scan:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        result = await db.execute(
            select(OrgMember).where(
                OrgMember.user_id == payload["sub"], OrgMember.org_id == scan.org_id
            )
        )
        if result.scalar_one_or_none() is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await websocket.accept()
    # Send a snapshot first
    await websocket.send_text(
        json.dumps(
            {
                "type": "snapshot",
                "scan_id": scan_id,
                "status": scan.status.value,
                "progress": scan.progress,
                "summary": scan.summary or {},
            }
        )
    )
    try:
        async for event in subscribe_scan(scan_id):
            await websocket.send_text(json.dumps(event))
    except WebSocketDisconnect:
        return
