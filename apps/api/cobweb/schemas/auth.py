from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    org_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    requires_mfa: bool = False


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    is_active: bool
    is_superuser: bool
    mfa_enabled: bool
    org_id: str | None = None
    org_name: str | None = None
    role: str | None = None


class MfaEnrollResponse(BaseModel):
    secret: str
    provisioning_uri: str


class MfaVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class ApiTokenCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ApiTokenResponse(BaseModel):
    id: str
    name: str
    plaintext: str | None = None  # returned only on create
    created_at: str
    expires_at: str | None = None
