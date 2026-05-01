"""/api/v1/tokens — API Token management for CI/CD."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.core.deps import CurrentUser, get_current_user
from cobweb.core.rbac import require
from cobweb.core.security import generate_api_key
from cobweb.db.base import get_db
from cobweb.models.api_token import ApiToken
from cobweb.services.audit_service import log_event

router = APIRouter(tags=["tokens"])


class TokenCreate(BaseModel):
    name: str
    expires_at: str | None = None  # ISO 8601


class TokenResponse(BaseModel):
    id: str
    name: str
    last_used_at: str | None = None
    expires_at: str | None = None
    created_at: str


class TokenCreateResponse(TokenResponse):
    plaintext: str  # shown once


def _out(t: ApiToken) -> TokenResponse:
    return TokenResponse(
        id=t.id, name=t.name,
        last_used_at=t.last_used_at.isoformat() if t.last_used_at else None,
        expires_at=t.expires_at.isoformat() if t.expires_at else None,
        created_at=t.created_at.isoformat(),
    )


@router.get("/tokens", response_model=list[TokenResponse])
async def list_tokens(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "apitoken:manage")
    res = await db.execute(
        select(ApiToken)
        .where(ApiToken.org_id == current.org_id)
        .order_by(ApiToken.created_at.desc())
    )
    return [_out(t) for t in res.scalars().all()]


@router.post("/tokens", response_model=TokenCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_token(
    body: TokenCreate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "apitoken:manage")
    plaintext, digest = generate_api_key()
    expires = (
        datetime.fromisoformat(body.expires_at.replace("Z", "+00:00"))
        if body.expires_at
        else None
    )
    token = ApiToken(
        org_id=current.org_id,
        name=body.name,
        token_hash=digest,
        expires_at=expires,
        created_by=current.user.id,
    )
    db.add(token)
    await db.flush()
    await log_event(
        db, org_id=current.org_id, actor_id=current.user.id,
        action="apitoken.create", resource_type="apitoken", resource_id=token.id,
        payload={"name": body.name},
    )
    await db.commit()
    base = _out(token)
    return TokenCreateResponse(plaintext=plaintext, **base.model_dump())


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(
    token_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "apitoken:manage")
    token = await db.get(ApiToken, token_id)
    if not token or token.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
    await db.delete(token)
    await log_event(
        db, org_id=current.org_id, actor_id=current.user.id,
        action="apitoken.revoke", resource_type="apitoken", resource_id=token_id,
    )
    await db.commit()
