from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl


class TargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    base_url: HttpUrl
    scope_includes: list[str] = []
    scope_excludes: list[str] = []


class TargetResponse(BaseModel):
    id: str
    project_id: str
    name: str
    base_url: str
    scope_includes: list[str]
    scope_excludes: list[str]
    status: str
    verification_token: str | None = None
    created_at: str
