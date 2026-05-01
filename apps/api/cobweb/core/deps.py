"""FastAPI dependency-injection helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.core.security import decode_token, hash_api_key
from cobweb.core.settings import get_settings
from cobweb.db.base import get_db
from cobweb.models.api_token import ApiToken
from cobweb.models.org import OrgMember, OrgRole
from cobweb.models.user import User


@dataclass
class CurrentUser:
    user: User
    org_id: str | None
    role: OrgRole | None


async def _get_user_from_bearer(
    authorization: str | None,
    db: AsyncSession,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from None
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")

    user = await db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found / inactive")
    return user


async def _resolve_org_membership(
    db: AsyncSession, user_id: str, org_id: str | None
) -> tuple[str | None, OrgRole | None]:
    if not org_id:
        # default to first membership
        result = await db.execute(
            select(OrgMember).where(OrgMember.user_id == user_id).limit(1)
        )
        member = result.scalar_one_or_none()
        return (member.org_id, member.role) if member else (None, None)

    result = await db.execute(
        select(OrgMember).where(
            OrgMember.user_id == user_id, OrgMember.org_id == org_id
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this org")
    return member.org_id, member.role


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    x_org_id: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    user = await _get_user_from_bearer(authorization, db)
    org_id, role = await _resolve_org_membership(db, user.id, x_org_id)
    return CurrentUser(user=user, org_id=org_id, role=role)


async def get_current_user_browser(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_org_id: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Like get_current_user but also accepts ?_t=<jwt> query param for direct
    browser links (anchor tags / iframes can't set Authorization header)."""
    if not authorization:
        t = request.query_params.get("_t")
        if t:
            authorization = f"Bearer {t}"
    user = await _get_user_from_bearer(authorization, db)
    org_id, role = await _resolve_org_membership(db, user.id, x_org_id)
    return CurrentUser(user=user, org_id=org_id, role=role)


async def require_worker_token(
    x_worker_token: Annotated[str | None, Header()] = None,
) -> None:
    """Static-token auth for internal scanner workers ingesting findings.

    Workers run inside the same K8s namespace; the token is mounted from a Secret.
    """
    expected = get_settings().worker_token
    if not x_worker_token or x_worker_token != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid worker token")


async def get_api_key_principal(
    x_api_key: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> ApiToken:
    if not x_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing API key")
    digest = hash_api_key(x_api_key)
    result = await db.execute(select(ApiToken).where(ApiToken.token_hash == digest))
    token = result.scalar_one_or_none()
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    return token
