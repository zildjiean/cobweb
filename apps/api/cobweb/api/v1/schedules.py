"""/api/v1 — scan schedule CRUD + immediate run."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.core.deps import CurrentUser, get_current_user
from cobweb.core.rbac import require
from cobweb.db.base import get_db
from cobweb.models.scan import ScanProfile
from cobweb.models.schedule import ScanSchedule, ScheduleFrequency
from cobweb.models.target import Target
from cobweb.schemas.schedule import (
    ScheduleCreate,
    ScheduleResponse,
    ScheduleUpdate,
)
from cobweb.services import scan_orchestrator
from cobweb.services.audit_service import log_event
from cobweb.services.scheduler_service import compute_next_run

router = APIRouter(prefix="/schedules", tags=["schedules"])


def _to_response(s: ScanSchedule) -> ScheduleResponse:
    return ScheduleResponse(
        id=s.id,
        org_id=s.org_id,
        project_id=s.project_id,
        target_id=s.target_id,
        name=s.name,
        profile=s.profile.value if hasattr(s.profile, "value") else s.profile,
        engine=s.engine,
        frequency=s.frequency.value if hasattr(s.frequency, "value") else s.frequency,
        hour_of_day=s.hour_of_day,
        day_of_week=s.day_of_week,
        day_of_month=s.day_of_month,
        enabled=s.enabled,
        next_run_at=s.next_run_at.isoformat() if s.next_run_at else None,
        last_run_at=s.last_run_at.isoformat() if s.last_run_at else None,
        last_scan_id=s.last_scan_id,
        created_at=s.created_at.isoformat(),
        updated_at=s.updated_at.isoformat(),
    )


@router.get("", response_model=list[ScheduleResponse])
async def list_schedules(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ScheduleResponse]:
    require(current.role, "scan:create")
    res = await db.execute(
        select(ScanSchedule)
        .where(ScanSchedule.org_id == current.org_id)
        .order_by(ScanSchedule.created_at.desc())
    )
    return [_to_response(s) for s in res.scalars().all()]


@router.post("", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    payload: ScheduleCreate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScheduleResponse:
    require(current.role, "scan:create")
    target = await db.get(Target, payload.target_id)
    if not target or target.org_id != current.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target not found")

    s = ScanSchedule(
        org_id=current.org_id,
        project_id=target.project_id,
        target_id=target.id,
        name=payload.name,
        profile=ScanProfile(payload.profile),
        engine=payload.engine,
        frequency=ScheduleFrequency(payload.frequency),
        hour_of_day=payload.hour_of_day,
        day_of_week=payload.day_of_week,
        day_of_month=payload.day_of_month,
        enabled=payload.enabled,
        created_by=current.user.id,
    )
    s.next_run_at = compute_next_run(s)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    await log_event(
        db,
        actor_id=current.user.id,
        org_id=current.org_id,
        action="schedule.create",
        resource_type="schedule",
        resource_id=s.id,
        payload={"target_id": s.target_id, "frequency": payload.frequency},
    )
    return _to_response(s)


async def _get_owned(db: AsyncSession, schedule_id: str, org_id: str) -> ScanSchedule:
    s = await db.get(ScanSchedule, schedule_id)
    if not s or s.org_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
    return s


@router.patch("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: str,
    payload: ScheduleUpdate,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScheduleResponse:
    require(current.role, "scan:create")
    s = await _get_owned(db, schedule_id, current.org_id)

    cadence_changed = False
    if payload.name is not None:
        s.name = payload.name
    if payload.profile is not None:
        s.profile = ScanProfile(payload.profile)
    if payload.engine is not None:
        s.engine = payload.engine
    if payload.frequency is not None:
        s.frequency = ScheduleFrequency(payload.frequency)
        cadence_changed = True
    if payload.hour_of_day is not None:
        s.hour_of_day = payload.hour_of_day
        cadence_changed = True
    if payload.day_of_week is not None:
        s.day_of_week = payload.day_of_week
        cadence_changed = True
    if payload.day_of_month is not None:
        s.day_of_month = payload.day_of_month
        cadence_changed = True
    if payload.enabled is not None:
        s.enabled = payload.enabled
        if payload.enabled:
            cadence_changed = True  # re-arm next_run_at when re-enabling

    if cadence_changed and s.enabled:
        s.next_run_at = compute_next_run(s)

    await db.commit()
    await db.refresh(s)
    await log_event(
        db,
        actor_id=current.user.id,
        org_id=current.org_id,
        action="schedule.update",
        resource_type="schedule",
        resource_id=s.id,
        payload=payload.model_dump(exclude_none=True),
    )
    return _to_response(s)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    require(current.role, "scan:create")
    s = await _get_owned(db, schedule_id, current.org_id)
    await db.delete(s)
    await db.commit()
    await log_event(
        db,
        actor_id=current.user.id,
        org_id=current.org_id,
        action="schedule.delete",
        resource_type="schedule",
        resource_id=schedule_id,
        payload={"name": s.name},
    )


@router.post("/{schedule_id}/run", response_model=ScheduleResponse)
async def run_schedule_now(
    schedule_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScheduleResponse:
    """Trigger this schedule immediately and recompute the next run."""
    require(current.role, "scan:create")
    s = await _get_owned(db, schedule_id, current.org_id)

    try:
        scan = await scan_orchestrator.create_scan(
            db,
            org_id=s.org_id,
            project_id=s.project_id,
            target_id=s.target_id,
            profile=s.profile,
            triggered_by=current.user.id,
            engine=s.engine,
            config={
                "scheduled": True,
                "schedule_id": s.id,
                "schedule_name": s.name,
                "manual_trigger": True,
            },
        )
    except scan_orchestrator.ScanError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    now = datetime.now(timezone.utc)
    s.last_run_at = now
    s.last_scan_id = scan.id
    if s.enabled:
        s.next_run_at = compute_next_run(s, now=now)
    await db.commit()
    await db.refresh(s)
    return _to_response(s)
