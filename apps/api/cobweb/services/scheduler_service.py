"""Background scheduler — fires due ScanSchedules every minute.

Runs as an asyncio task started in the API lifespan. No new dep — uses
asyncio.sleep + a DB poll. Queue depth is small (one row per active schedule)
so this scales fine for POC; if it ever doesn't, swap for APScheduler.

next_run_at is computed and stored after each fire so the loop is just a
"select where enabled and next_run_at <= now" query.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cobweb.db.base import get_sessionmaker
from cobweb.models.schedule import ScanSchedule, ScheduleFrequency

POLL_INTERVAL_SEC = 60


def compute_next_run(
    schedule: ScanSchedule, *, now: datetime | None = None
) -> datetime:
    """Compute the next firing time strictly *after* `now` (default UTC now).

    Cadence semantics:
      hourly  → top of next hour
      daily   → today at hour_of_day if still ahead, else tomorrow
      weekly  → next occurrence of day_of_week at hour_of_day
      monthly → next occurrence of day_of_month at hour_of_day in this/next month
    """
    now = now or datetime.now(timezone.utc)
    freq = schedule.frequency
    if freq == ScheduleFrequency.HOURLY:
        nxt = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return nxt
    if freq == ScheduleFrequency.DAILY:
        candidate = now.replace(
            hour=schedule.hour_of_day, minute=0, second=0, microsecond=0
        )
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate
    if freq == ScheduleFrequency.WEEKLY:
        # weekday() returns 0=Mon..6=Sun — same convention as our day_of_week
        days_ahead = (schedule.day_of_week - now.weekday()) % 7
        candidate = now.replace(
            hour=schedule.hour_of_day, minute=0, second=0, microsecond=0
        ) + timedelta(days=days_ahead)
        if candidate <= now:
            candidate += timedelta(days=7)
        return candidate
    if freq == ScheduleFrequency.MONTHLY:
        target_day = min(schedule.day_of_month, 28)  # capped at 28 to dodge Feb
        candidate = now.replace(
            day=target_day,
            hour=schedule.hour_of_day,
            minute=0,
            second=0,
            microsecond=0,
        )
        if candidate <= now:
            # roll to next month
            year = now.year + (1 if now.month == 12 else 0)
            month = 1 if now.month == 12 else now.month + 1
            candidate = candidate.replace(year=year, month=month)
        return candidate
    raise ValueError(f"unknown frequency: {freq}")


async def _fire_schedule(db: AsyncSession, schedule: ScanSchedule) -> None:
    """Create a Scan from this schedule, recompute next_run_at, commit."""
    # Lazy-imported to avoid circular import (scan_orchestrator → settings → DB → schedule)
    from cobweb.services import scan_orchestrator

    now = datetime.now(timezone.utc)
    last_scan_id: str | None = None
    try:
        scan = await scan_orchestrator.create_scan(
            db,
            org_id=schedule.org_id,
            project_id=schedule.project_id,
            target_id=schedule.target_id,
            profile=schedule.profile,
            triggered_by=schedule.created_by,
            engine=schedule.engine,
            config={
                "scheduled": True,
                "schedule_id": schedule.id,
                "schedule_name": schedule.name,
            },
        )
        last_scan_id = scan.id
    except scan_orchestrator.ScanError as exc:
        # Don't crash the loop — most likely cause is target unverified or deleted.
        # Log it and roll the next_run forward so we don't hammer the failing target.
        logger.warning(
            "schedule {} ({}) skipped: {}", schedule.id, schedule.name, exc
        )

    schedule.last_run_at = now
    if last_scan_id:
        schedule.last_scan_id = last_scan_id
    schedule.next_run_at = compute_next_run(schedule, now=now)
    await db.commit()
    logger.info(
        "schedule {} ({}) fired → scan={} next={}",
        schedule.id, schedule.name, last_scan_id or "skipped", schedule.next_run_at,
    )


async def _tick(Session) -> None:
    async with Session() as db:
        now = datetime.now(timezone.utc)
        res = await db.execute(
            select(ScanSchedule).where(
                ScanSchedule.enabled.is_(True),
                ScanSchedule.next_run_at.isnot(None),
                ScanSchedule.next_run_at <= now,
            )
        )
        due = list(res.scalars().all())
        for schedule in due:
            try:
                await _fire_schedule(db, schedule)
            except Exception as exc:  # noqa: BLE001
                logger.exception("schedule {} firing crashed: {}", schedule.id, exc)


async def scheduler_loop() -> None:
    """Long-running task that fires due schedules every POLL_INTERVAL_SEC."""
    Session = get_sessionmaker()
    logger.info("scheduler loop started (poll every {}s)", POLL_INTERVAL_SEC)
    while True:
        try:
            await _tick(Session)
        except asyncio.CancelledError:
            logger.info("scheduler loop cancelled")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("scheduler tick crashed: {}", exc)
        await asyncio.sleep(POLL_INTERVAL_SEC)
