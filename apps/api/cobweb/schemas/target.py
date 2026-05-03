from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

AuthType = Literal["header", "cookie"]


class HeaderAuth(BaseModel):
    type: Literal["header"] = "header"
    name: str = Field(min_length=1, max_length=128)  # e.g. "Authorization"
    value: str = Field(min_length=1, max_length=4096)  # e.g. "Bearer eyJ…"


class CookieAuth(BaseModel):
    type: Literal["cookie"] = "cookie"
    value: str = Field(min_length=1, max_length=4096)  # e.g. "session=abc; csrf=xyz"


# Discriminated union — pydantic picks the right one based on the "type" field
AuthConfig = HeaderAuth | CookieAuth


class TargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    base_url: HttpUrl
    scope_includes: list[str] = []
    scope_excludes: list[str] = []
    auth: AuthConfig | None = None


class TargetUpdate(BaseModel):
    """Partial update — only fields the user actually wants to change. To clear
    the auth, send `clear_auth: true`. Sending `auth: <new>` overwrites it."""
    auth: AuthConfig | None = None
    clear_auth: bool = False


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
    has_auth: bool = False
    auth_type: AuthType | None = None  # the *type* is safe to expose; the value isn't
