"""/api/v1 — LLM org settings + per-finding translation."""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.core.crypto import decrypt, encrypt
from cobweb.core.deps import CurrentUser, get_current_user
from cobweb.core.rbac import require
from cobweb.db.base import get_db
from cobweb.models.llm import (
    DEFAULT_PROMPT_TEMPLATE,
    REMEDIATION_PROMPT_TEMPLATE,
    FindingRemediation,
    FindingTranslation,
    OrgLLMSettings,
)
from cobweb.models.scan import Finding
from cobweb.schemas.llm import (
    LLMSettingsResponse,
    LLMSettingsUpdate,
    RemediationRequest,
    RemediationResponse,
    TranslateRequest,
    TranslateResponse,
)
from cobweb.services.audit_service import log_event
from cobweb.services.llm import LLMError, get_provider

router = APIRouter(tags=["llm"])


def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()


def _settings_out(s: OrgLLMSettings | None) -> LLMSettingsResponse:
    if s is None:
        return LLMSettingsResponse(
            provider=None,
            model=None,
            has_api_key=False,
            prompt_template=DEFAULT_PROMPT_TEMPLATE,
            updated_at=None,
        )
    return LLMSettingsResponse(
        provider=s.provider,  # type: ignore[arg-type]
        model=s.model,
        has_api_key=bool(s.api_key_ciphertext),
        prompt_template=s.prompt_template,
        updated_at=s.updated_at.isoformat() if s.updated_at else None,
    )


def _build_finding_user_text(f: Finding) -> str:
    """Compose the content the model translates — keeps fields labelled so the
    translation preserves structure."""
    blocks: list[str] = [f"Title: {f.name}"]
    blocks.append(f"Severity: {f.severity.value if hasattr(f.severity, 'value') else f.severity}")
    if f.cve:
        blocks.append(f"CVE: {f.cve}")
    if f.cwe:
        blocks.append(f"CWE: {f.cwe}")
    if f.cvss:
        blocks.append(f"CVSS: {f.cvss}")
    blocks.append(f"Matched at: {f.matched_at}")
    if f.description:
        blocks.append(f"\nDescription:\n{f.description}")
    if f.remediation:
        blocks.append(f"\nRemediation:\n{f.remediation}")
    return "\n".join(blocks)


_HTTP_SNIPPET_LIMIT = 2000  # keep request/response context small for the model


def _build_finding_remediation_text(f: Finding) -> str:
    """Compose the user payload the remediation model sees. Includes truncated
    request/response for context but caps each at 2 KB so cheap models don't
    choke on long pages."""
    blocks: list[str] = [
        f"Title: {f.name}",
        f"Template: {f.template_id}",
        f"Severity: {f.severity.value if hasattr(f.severity, 'value') else f.severity}",
    ]
    if f.cve:
        blocks.append(f"CVE: {f.cve}")
    if f.cwe:
        blocks.append(f"CWE: {f.cwe}")
    if f.cvss:
        blocks.append(f"CVSS: {f.cvss}")
    blocks.append(f"Matched URL: {f.matched_at}")
    if f.matcher_name:
        blocks.append(f"Matcher: {f.matcher_name}")
    if f.description:
        blocks.append(f"\nScanner description:\n{f.description}")
    if f.remediation:
        blocks.append(f"\nGeneric remediation hint from scanner:\n{f.remediation}")
    if f.request:
        snippet = f.request[:_HTTP_SNIPPET_LIMIT]
        truncated = " (truncated)" if len(f.request) > _HTTP_SNIPPET_LIMIT else ""
        blocks.append(f"\nHTTP request{truncated}:\n```\n{snippet}\n```")
    if f.response:
        snippet = f.response[:_HTTP_SNIPPET_LIMIT]
        truncated = " (truncated)" if len(f.response) > _HTTP_SNIPPET_LIMIT else ""
        blocks.append(f"\nHTTP response{truncated}:\n```\n{snippet}\n```")
    return "\n".join(blocks)


@router.get("/org/llm-settings", response_model=LLMSettingsResponse)
async def get_llm_settings(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LLMSettingsResponse:
    require(current.role, "llm:configure")
    s = await db.get(OrgLLMSettings, current.org_id)
    return _settings_out(s)


@router.put("/org/llm-settings", response_model=LLMSettingsResponse)
async def update_llm_settings(
    payload: LLMSettingsUpdate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LLMSettingsResponse:
    require(current.role, "llm:configure")
    existing = await db.get(OrgLLMSettings, current.org_id)
    api_key_ct: str | None
    if payload.api_key:
        api_key_ct = encrypt(payload.api_key)
    elif existing:
        api_key_ct = existing.api_key_ciphertext
    else:
        api_key_ct = None
    if existing is None:
        existing = OrgLLMSettings(
            org_id=current.org_id,
            provider=payload.provider,
            model=payload.model,
            api_key_ciphertext=api_key_ct,
            prompt_template=payload.prompt_template,
            updated_by=current.user.id,
        )
        db.add(existing)
    else:
        existing.provider = payload.provider
        existing.model = payload.model
        existing.api_key_ciphertext = api_key_ct
        existing.prompt_template = payload.prompt_template
        existing.updated_by = current.user.id
    await db.commit()
    await db.refresh(existing)
    await log_event(
        db,
        actor_id=current.user.id,
        org_id=current.org_id,
        action="llm.settings.update",
        resource_type="org",
        resource_id=current.org_id,
        payload={"provider": payload.provider, "model": payload.model},
    )
    return _settings_out(existing)


@router.post(
    "/findings/{finding_id}/translate",
    response_model=TranslateResponse,
)
async def translate_finding(
    finding_id: str,
    payload: TranslateRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TranslateResponse:
    require(current.role, "finding:translate")

    finding = await db.get(Finding, finding_id)
    if not finding or finding.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Finding not found")

    settings = await db.get(OrgLLMSettings, current.org_id)
    if (
        not settings
        or not settings.api_key_ciphertext
        or not settings.provider
        or not settings.model
    ):
        raise HTTPException(
            status.HTTP_412_PRECONDITION_FAILED,
            "LLM not configured — admin must set provider/model/api_key first",
        )

    prompt = (payload.custom_prompt or settings.prompt_template).strip()
    prompt_hash = _hash_prompt(prompt + "|" + settings.provider + "|" + settings.model)

    if not payload.refresh:
        result = await db.execute(
            select(FindingTranslation).where(
                FindingTranslation.finding_id == finding.id,
                FindingTranslation.lang == payload.lang,
                FindingTranslation.prompt_hash == prompt_hash,
            )
        )
        cached = result.scalar_one_or_none()
        if cached:
            return TranslateResponse(
                finding_id=finding.id,
                lang=cached.lang,
                provider=cached.provider,
                model=cached.model,
                content=cached.content,
                cached=True,
                tokens_in=cached.tokens_in,
                tokens_out=cached.tokens_out,
                created_at=cached.created_at.isoformat(),
            )

    try:
        api_key = decrypt(settings.api_key_ciphertext)
    except ValueError:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "stored api_key is corrupt — re-save in settings",
        )

    provider = get_provider(settings.provider)
    user_text = _build_finding_user_text(finding)
    try:
        resp = await provider.generate(
            model=settings.model,
            system=prompt,
            user=user_text,
            api_key=api_key,
        )
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

    row = FindingTranslation(
        finding_id=finding.id,
        org_id=current.org_id,
        lang=payload.lang,
        provider=settings.provider,
        model=settings.model,
        prompt_hash=prompt_hash,
        content=resp.content,
        tokens_in=resp.tokens_in,
        tokens_out=resp.tokens_out,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await log_event(
        db,
        actor_id=current.user.id,
        org_id=current.org_id,
        action="finding.translate",
        resource_type="finding",
        resource_id=finding.id,
        payload={
            "provider": settings.provider,
            "model": settings.model,
            "tokens_in": resp.tokens_in,
            "tokens_out": resp.tokens_out,
        },
    )
    return TranslateResponse(
        finding_id=finding.id,
        lang=row.lang,
        provider=row.provider,
        model=row.model,
        content=row.content,
        cached=False,
        tokens_in=row.tokens_in,
        tokens_out=row.tokens_out,
        created_at=row.created_at.isoformat(),
    )


@router.post(
    "/findings/{finding_id}/remediation",
    response_model=RemediationResponse,
)
async def remediate_finding(
    finding_id: str,
    payload: RemediationRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RemediationResponse:
    require(current.role, "finding:remediate")

    finding = await db.get(Finding, finding_id)
    if not finding or finding.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Finding not found")

    settings = await db.get(OrgLLMSettings, current.org_id)
    if (
        not settings
        or not settings.api_key_ciphertext
        or not settings.provider
        or not settings.model
    ):
        raise HTTPException(
            status.HTTP_412_PRECONDITION_FAILED,
            "LLM not configured — admin must set provider/model/api_key first",
        )

    prompt = (payload.custom_prompt or REMEDIATION_PROMPT_TEMPLATE).strip()
    prompt_hash = _hash_prompt(prompt + "|" + settings.provider + "|" + settings.model)

    if not payload.refresh:
        result = await db.execute(
            select(FindingRemediation).where(
                FindingRemediation.finding_id == finding.id,
                FindingRemediation.prompt_hash == prompt_hash,
            )
        )
        cached = result.scalar_one_or_none()
        if cached:
            return RemediationResponse(
                finding_id=finding.id,
                provider=cached.provider,
                model=cached.model,
                content=cached.content,
                cached=True,
                tokens_in=cached.tokens_in,
                tokens_out=cached.tokens_out,
                created_at=cached.created_at.isoformat(),
            )

    try:
        api_key = decrypt(settings.api_key_ciphertext)
    except ValueError:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "stored api_key is corrupt — re-save in settings",
        )

    provider = get_provider(settings.provider)
    user_text = _build_finding_remediation_text(finding)
    try:
        resp = await provider.generate(
            model=settings.model,
            system=prompt,
            user=user_text,
            api_key=api_key,
        )
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

    row = FindingRemediation(
        finding_id=finding.id,
        org_id=current.org_id,
        provider=settings.provider,
        model=settings.model,
        prompt_hash=prompt_hash,
        content=resp.content,
        tokens_in=resp.tokens_in,
        tokens_out=resp.tokens_out,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await log_event(
        db,
        actor_id=current.user.id,
        org_id=current.org_id,
        action="finding.remediate",
        resource_type="finding",
        resource_id=finding.id,
        payload={
            "provider": settings.provider,
            "model": settings.model,
            "tokens_in": resp.tokens_in,
            "tokens_out": resp.tokens_out,
        },
    )
    return RemediationResponse(
        finding_id=finding.id,
        provider=row.provider,
        model=row.model,
        content=row.content,
        cached=False,
        tokens_in=row.tokens_in,
        tokens_out=row.tokens_out,
        created_at=row.created_at.isoformat(),
    )
