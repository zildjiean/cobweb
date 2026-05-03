from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from cobweb.db.base import Base, TimestampMixin, enum_col, new_uuid
from cobweb.models.scan import ScanProfile


class ScheduleFrequency(str, enum.Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ScanSchedule(Base, TimestampMixin):
    """Org-managed schedule that fires a Scan against a Target on a recurring basis.

    Cadence model is a small dropdown rather than full cron — keeps the UI simple
    and removes a dep on croniter. Fields used per frequency:
        hourly  : (none — fires at the top of each hour)
        daily   : hour_of_day (0-23)
        weekly  : hour_of_day, day_of_week (0=Mon..6=Sun)
        monthly : hour_of_day, day_of_month (1-28; capped to dodge Feb edge cases)

    A background loop in the API lifespan polls every minute, fires any schedule
    where enabled AND next_run_at <= now, and recomputes next_run_at after.
    """

    __tablename__ = "scan_schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    target_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("targets.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    profile: Mapped[ScanProfile] = mapped_column(
        enum_col(ScanProfile, name="scan_profile"), default=ScanProfile.QUICK
    )
    engine: Mapped[str] = mapped_column(String(32), default="nuclei")

    frequency: Mapped[ScheduleFrequency] = mapped_column(
        enum_col(ScheduleFrequency, name="schedule_frequency"), nullable=False
    )
    hour_of_day: Mapped[int] = mapped_column(Integer, default=0)  # 0-23
    day_of_week: Mapped[int] = mapped_column(Integer, default=0)  # 0=Mon..6=Sun
    day_of_month: Mapped[int] = mapped_column(Integer, default=1)  # 1-28

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_scan_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
