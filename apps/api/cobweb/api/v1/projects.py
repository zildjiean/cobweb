"""/api/v1/projects — project & target CRUD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.core.deps import CurrentUser, get_current_user
from cobweb.core.rbac import require
from cobweb.core.security import generate_api_key
from cobweb.core.settings import get_settings
from cobweb.db.base import get_db
from cobweb.models.project import Project
from cobweb.models.target import Target, TargetStatus
from cobweb.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from cobweb.schemas.target import TargetCreate, TargetResponse
from cobweb.services.audit_service import log_event
from cobweb.services.target_verification import VerificationError, verify_target

router = APIRouter(tags=["projects"])


def _project_out(p: Project) -> ProjectResponse:
    return ProjectResponse(
        id=p.id, org_id=p.org_id, name=p.name, slug=p.slug,
        description=p.description, created_at=p.created_at.isoformat(),
    )


def _target_out(t: Target) -> TargetResponse:
    return TargetResponse(
        id=t.id, project_id=t.project_id, name=t.name, base_url=t.base_url,
        scope_includes=t.scope_includes or [], scope_excludes=t.scope_excludes or [],
        status=t.status.value, verification_token=t.verification_token,
        created_at=t.created_at.isoformat(),
    )


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "project:view")
    result = await db.execute(select(Project).where(Project.org_id == current.org_id))
    return [_project_out(p) for p in result.scalars().all()]


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "project:create")
    project = Project(
        org_id=current.org_id, name=body.name, slug=body.slug, description=body.description
    )
    db.add(project)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Slug already exists in org") from None

    await log_event(
        db, org_id=current.org_id, actor_id=current.user.id,
        action="project.create", resource_type="project", resource_id=project.id,
        payload={"name": body.name, "slug": body.slug},
    )
    await db.commit()
    return _project_out(project)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "project:update")
    project = await db.get(Project, project_id)
    if not project or project.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    await log_event(
        db, org_id=current.org_id, actor_id=current.user.id,
        action="project.update", resource_type="project", resource_id=project.id,
        payload=body.model_dump(exclude_none=True),
    )
    await db.commit()
    return _project_out(project)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "project:delete")
    project = await db.get(Project, project_id)
    if not project or project.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    await db.delete(project)
    await log_event(
        db, org_id=current.org_id, actor_id=current.user.id,
        action="project.delete", resource_type="project", resource_id=project_id,
    )
    await db.commit()


# ── Targets ─────────────────────────────────────────────────────────
@router.get("/targets", response_model=list[TargetResponse])
async def list_all_targets(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List every target visible to the current org. Convenient for UI lookups."""
    require(current.role, "target:view")
    result = await db.execute(
        select(Target)
        .join(Project, Target.project_id == Project.id)
        .where(Project.org_id == current.org_id)
    )
    return [_target_out(t) for t in result.scalars().all()]


@router.get("/projects/{project_id}/targets", response_model=list[TargetResponse])
async def list_targets(
    project_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "target:view")
    project = await db.get(Project, project_id)
    if not project or project.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    result = await db.execute(select(Target).where(Target.project_id == project_id))
    return [_target_out(t) for t in result.scalars().all()]


@router.post(
    "/projects/{project_id}/targets",
    response_model=TargetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_target(
    project_id: str,
    body: TargetCreate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "target:create")
    project = await db.get(Project, project_id)
    if not project or project.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")

    settings = get_settings()
    skip_verify = settings.dev_skip_target_verification

    verification_token = "cobweb-verify-" + generate_api_key()[0].split("_", 1)[1][:24]
    target = Target(
        project_id=project_id,
        name=body.name,
        base_url=str(body.base_url),
        scope_includes=body.scope_includes,
        scope_excludes=body.scope_excludes,
        status=(
            TargetStatus.VERIFIED if skip_verify else TargetStatus.PENDING_VERIFICATION
        ),
        verification_token=None if skip_verify else verification_token,
    )
    db.add(target)
    await db.flush()
    await log_event(
        db, org_id=current.org_id, actor_id=current.user.id,
        action="target.create", resource_type="target", resource_id=target.id,
        payload={
            "base_url": str(body.base_url),
            "auto_verified": skip_verify,
        },
    )
    await db.commit()
    return _target_out(target)


@router.delete("/targets/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_target_endpoint(
    target_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a target. Cascades to its scans, findings, and vulnerabilities."""
    require(current.role, "target:delete")
    target = await db.get(Target, target_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target not found")
    project = await db.get(Project, target.project_id)
    if not project or project.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target not found")

    await db.delete(target)
    await log_event(
        db, org_id=current.org_id, actor_id=current.user.id,
        action="target.delete", resource_type="target", resource_id=target_id,
        payload={"name": target.name, "base_url": target.base_url},
    )
    await db.commit()


@router.post("/targets/{target_id}/verify", response_model=TargetResponse)
async def verify_target_endpoint(
    target_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require(current.role, "target:update")
    target = await db.get(Target, target_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target not found")
    project = await db.get(Project, target.project_id)
    if not project or project.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target not found")

    try:
        method = await verify_target(target)
    except VerificationError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None

    target.status = TargetStatus.VERIFIED
    await log_event(
        db, org_id=current.org_id, actor_id=current.user.id,
        action="target.verified", resource_type="target", resource_id=target.id,
        payload={"method": method},
    )
    await db.commit()
    return _target_out(target)
