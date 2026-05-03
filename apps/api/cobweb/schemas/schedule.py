from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ScheduleFrequencyLiteral = Literal["hourly", "daily", "weekly", "monthly"]
ProfileLiteral = Literal["quick", "high", "full", "custom"]


class ScheduleBase(BaseModel):
    target_id: str
    name: str = Field(min_length=1, max_length=255)
    profile: ProfileLiteral = "quick"
    engine: str = "nuclei"
    frequency: ScheduleFrequencyLiteral
    hour_of_day: int = Field(0, ge=0, le=23)
    day_of_week: int = Field(0, ge=0, le=6)  # 0=Mon..6=Sun
    day_of_month: int = Field(1, ge=1, le=28)
    enabled: bool = True


class ScheduleCreate(ScheduleBase):
    pass


class ScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    profile: ProfileLiteral | None = None
    engine: str | None = None
    frequency: ScheduleFrequencyLiteral | None = None
    hour_of_day: int | None = Field(default=None, ge=0, le=23)
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    day_of_month: int | None = Field(default=None, ge=1, le=28)
    enabled: bool | None = None


class ScheduleResponse(ScheduleBase):
    id: str
    org_id: str
    project_id: str
    next_run_at: str | None
    last_run_at: str | None
    last_scan_id: str | None
    created_at: str
    updated_at: str
