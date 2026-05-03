from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ScanCreate(BaseModel):
    target_id: str
    profile: Literal["quick", "high", "full", "custom"] = "quick"
    engine: Literal["nuclei", "zap"] = "nuclei"
    config: dict[str, Any] = Field(default_factory=dict)


class ScanResponse(BaseModel):
    id: str
    org_id: str
    project_id: str
    target_id: str
    profile: str
    engine: str
    status: str
    progress: int
    template_version: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error_message: str | None = None
    summary: dict[str, int] = Field(default_factory=dict)
    created_at: str


class FindingIngest(BaseModel):
    """Sent by scanner workers — single finding."""

    template_id: str
    name: str
    severity: Literal["critical", "high", "medium", "low", "info"]
    matched_at: str
    matcher_name: str | None = None
    description: str | None = None
    remediation: str | None = None
    cve: str | None = None
    cwe: str | None = None
    cvss: str | None = None
    request: str | None = None
    response: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class WorkerStatusUpdate(BaseModel):
    status: Literal["running", "completed", "failed", "cancelled"]
    progress: int | None = None
    error_message: str | None = None
    template_version: str | None = None


class FindingResponse(BaseModel):
    id: str
    scan_id: str
    target_id: str
    template_id: str
    name: str
    severity: str
    matched_at: str
    description: str | None = None
    remediation: str | None = None
    cve: str | None = None
    cwe: str | None = None
    dedupe_hash: str
    created_at: str


class FindingAttackDetails(BaseModel):
    """Forensic fields extracted from a finding's raw payload — what was sent, where, and what came back."""

    method: str | None = None
    parameter: str | None = None
    payload: str | None = None
    evidence: str | None = None
    input_vector: str | None = None
    confidence: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class FindingDetailResponse(FindingResponse):
    """Full finding payload — includes request/response/raw for the issue detail view."""

    matcher_name: str | None = None
    cvss: str | None = None
    request: str | None = None
    response: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
    attack_details: FindingAttackDetails | None = None


class FindingBulkDelete(BaseModel):
    ids: list[str] = Field(..., min_length=1, max_length=500)


class FindingBulkDeleteResponse(BaseModel):
    deleted: int
    summary: dict[str, int]
