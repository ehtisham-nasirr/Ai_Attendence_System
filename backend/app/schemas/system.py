"""Settings, audit log, dashboard and background jobs."""

import datetime as dt
from typing import Any, Literal

from pydantic import Field

from app.schemas.common import ApiModel, InputModel, UtcDateTime


class SettingItem(ApiModel):
    key: str
    group: str
    value: Any
    default: Any
    description: str
    secret: bool
    is_set: bool


class SettingsUpdate(InputModel):
    """Only the keys to change. Secret values sent back as the mask are left unchanged."""

    values: dict[str, Any] = Field(min_length=1)


class AuditLogOut(ApiModel):
    id: int
    user_id: int | None
    user_name: str | None = None
    action: str
    entity: str
    entity_id: str | None
    old_values: dict[str, Any] | None
    new_values: dict[str, Any] | None
    ip: str | None
    user_agent: str | None
    created_at: UtcDateTime


class HourlyCount(ApiModel):
    hour: int
    count: int


class DepartmentCount(ApiModel):
    department_id: int | None
    department_name: str
    present: int
    absent: int
    late: int


class CameraHealthItem(ApiModel):
    camera_id: int
    name: str
    status: str
    mode: str | None
    fps_actual: float | None


class DashboardSummary(ApiModel):
    """FR-29 counters for today in the location's timezone."""

    work_date: dt.date
    expected: int
    present: int
    late: int
    absent: int
    on_leave: int
    in_office_now: int
    unknown_today: int
    hourly_arrivals: list[HourlyCount]
    departments: list[DepartmentCount]
    cameras: list[CameraHealthItem]
    load_levels: dict[str, int]


class JobOut(ApiModel):
    id: str
    kind: str
    status: Literal["queued", "running", "succeeded", "failed"]
    message: str | None = None
    result: dict[str, Any] | None = None
    file_available: bool = False
    created_at: UtcDateTime | None = None
