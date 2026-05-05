from __future__ import annotations

from pydantic import BaseModel


class SuppressionResponse(BaseModel):
    id: str
    org_id: str
    target_id: str
    dedupe_hash: str
    reason: str | None = None
    created_by: str | None = None
    expires_at: str
    created_at: str
