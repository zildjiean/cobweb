"""/api/v1/auth — login, register, MFA, me."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.core.deps import CurrentUser, get_current_user
from cobweb.core.security import (
    hash_password,
    issue_access_token,
    issue_refresh_token,
    new_totp_secret,
    totp_provisioning_uri,
    verify_password,
    verify_totp,
)
from cobweb.db.base import get_db
from cobweb.models.org import OrgMember, OrgRole, Organization
from cobweb.models.user import User
from cobweb.schemas.auth import (
    LoginRequest,
    MfaEnrollResponse,
    MfaVerifyRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from cobweb.core.settings import get_settings
from cobweb.services.audit_service import log_event
from cobweb.services.oidc_service import OidcError, OidcService

router = APIRouter(prefix="/auth", tags=["auth"])

_oidc = OidcService(get_settings())


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9-]+", "-", s.lower()).strip("-")
    return s or "org"


def _build_token(user: User, org_id: str | None, role: OrgRole | None) -> TokenResponse:
    claims = {"org_id": org_id, "role": role.value if role else None}
    return TokenResponse(
        access_token=issue_access_token(subject=user.id, claims=claims),
        refresh_token=issue_refresh_token(subject=user.id),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        email=body.email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
    )
    org = Organization(name=body.org_name, slug=_slugify(body.org_name))
    db.add_all([user, org])
    await db.flush()
    db.add(OrgMember(org_id=org.id, user_id=user.id, role=OrgRole.ADMIN))
    await log_event(
        db,
        org_id=org.id,
        actor_id=user.id,
        action="user.register",
        resource_type="user",
        resource_id=user.id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        payload={"email": body.email, "org": body.org_name},
    )
    await db.commit()
    return _build_token(user, org.id, OrgRole.ADMIN)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    if user.mfa_enabled:
        if not body.mfa_code:
            return TokenResponse(access_token="", refresh_token="", requires_mfa=True)
        if not user.mfa_secret or not verify_totp(user.mfa_secret, body.mfa_code):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid MFA code")

    member_q = await db.execute(select(OrgMember).where(OrgMember.user_id == user.id).limit(1))
    member = member_q.scalar_one_or_none()
    org_id = member.org_id if member else None
    role = member.role if member else None

    await log_event(
        db,
        org_id=org_id,
        actor_id=user.id,
        action="user.login",
        resource_type="user",
        resource_id=user.id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    return _build_token(user, org_id, role)


@router.get("/me", response_model=UserResponse)
async def me(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_name: str | None = None
    if current.org_id:
        org = (
            await db.execute(select(Organization).where(Organization.id == current.org_id))
        ).scalar_one_or_none()
        if org:
            org_name = org.name
    return UserResponse(
        id=current.user.id,
        email=current.user.email,
        full_name=current.user.full_name,
        is_active=current.user.is_active,
        is_superuser=current.user.is_superuser,
        mfa_enabled=current.user.mfa_enabled,
        org_id=current.org_id,
        org_name=org_name,
        role=current.role.value if current.role else None,
    )


@router.post("/mfa/enroll", response_model=MfaEnrollResponse)
async def mfa_enroll(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    secret = new_totp_secret()
    current.user.mfa_secret = secret
    current.user.mfa_enabled = False  # not enabled until verified
    await db.commit()
    return MfaEnrollResponse(
        secret=secret,
        provisioning_uri=totp_provisioning_uri(secret, account=current.user.email),
    )


@router.get("/oidc/login")
async def oidc_login():
    if not _oidc.configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "OIDC not configured")
    try:
        url, state = await _oidc.authorize_url()
    except OidcError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from None
    return {"authorize_url": url, "state": state}


@router.post("/oidc/exchange", response_model=TokenResponse)
async def oidc_exchange(
    body: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    code = body.get("code")
    if not code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing code")
    try:
        userinfo = await _oidc.exchange_code(code)
    except OidcError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from None
    email = userinfo.get("email")
    if not email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No email in OIDC userinfo")

    res = await db.execute(select(User).where(User.email == email))
    user = res.scalar_one_or_none()
    if user is None:
        # auto-provision: 1 user → 1 org (admin) on first login
        user = User(
            email=email,
            full_name=userinfo.get("name") or email.split("@")[0],
            password_hash="!oidc",  # password login disabled
        )
        org = Organization(name=f"{email.split('@')[0]}'s org",
                           slug=_slugify(email.split('@')[0]))
        db.add_all([user, org])
        await db.flush()
        db.add(OrgMember(org_id=org.id, user_id=user.id, role=OrgRole.ADMIN))
        await db.flush()

    member_q = await db.execute(
        select(OrgMember).where(OrgMember.user_id == user.id).limit(1)
    )
    member = member_q.scalar_one_or_none()
    org_id = member.org_id if member else None
    role = member.role if member else None

    await log_event(
        db, org_id=org_id, actor_id=user.id,
        action="user.login.oidc", resource_type="user", resource_id=user.id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    return _build_token(user, org_id, role)


@router.post("/mfa/verify", status_code=status.HTTP_204_NO_CONTENT)
async def mfa_verify(
    body: MfaVerifyRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current.user.mfa_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA not enrolled")
    if not verify_totp(current.user.mfa_secret, body.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid code")
    current.user.mfa_enabled = True
    await log_event(
        db,
        org_id=current.org_id,
        actor_id=current.user.id,
        action="user.mfa_enabled",
        resource_type="user",
        resource_id=current.user.id,
    )
    await db.commit()
