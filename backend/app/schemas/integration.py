"""HR/payroll integration schemas (FR-12, FR-24, FR-34, FR-35)."""

import datetime as dt
from typing import Literal

from facetrack_common.constants import AttendanceStatus
from pydantic import Field

from app.schemas.common import ApiModel, InputModel, UtcDateTime

ApiScope = Literal["attendance:read"]


def _default_scopes() -> list[ApiScope]:
    return ["attendance:read"]


class ApiClientCreate(InputModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[ApiScope] = Field(default_factory=_default_scopes, min_length=1)


class ApiClientUpdate(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    scopes: list[ApiScope] | None = Field(default=None, min_length=1)
    is_active: bool | None = None


class ApiClientOut(ApiModel):
    id: int
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    last_used_at: UtcDateTime | None
    created_at: UtcDateTime


class ApiClientCreated(ApiModel):
    client: ApiClientOut
    api_key: str = Field(description="Shown once. Only a hash is stored; a lost key must be replaced.")


class IntegrationAttendanceOut(ApiModel):
    """One finalised employee-day for payroll (§12 `/integration/attendance`)."""

    employee_code: str
    hr_external_id: str | None
    employee_name: str
    department_code: str | None
    work_date: dt.date
    shift_name: str | None
    check_in_at: UtcDateTime | None
    check_out_at: UtcDateTime | None
    worked_minutes: int
    late_minutes: int
    early_minutes: int
    overtime_minutes: int
    status: AttendanceStatus | None
    status_letter: str | None
    is_manual: bool
    finalized_at: UtcDateTime | None
    updated_at: UtcDateTime


class IntegrationJobAccepted(ApiModel):
    task: str
    detail: str
