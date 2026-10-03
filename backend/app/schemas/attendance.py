"""Attendance days and corrections (FR-20..FR-26)."""

import datetime as dt
from typing import Self

from facetrack_common.constants import AttendanceStatus, CorrectionField, CorrectionStatus
from pydantic import Field, model_validator

from app.schemas.common import ApiModel, AwareInput, InputModel, UtcDateTime


class AttendanceDayOut(ApiModel):
    id: int
    employee_id: int
    employee_code: str
    employee_name: str
    department_id: int | None
    department_name: str | None
    work_date: dt.date
    shift_id: int | None
    shift_name: str | None
    check_in_at: UtcDateTime | None
    check_out_at: UtcDateTime | None
    check_in_event_id: int | None
    check_out_event_id: int | None
    worked_minutes: int
    late_minutes: int
    early_minutes: int
    overtime_minutes: int
    status: AttendanceStatus | None
    status_letter: str | None
    is_manual: bool
    finalized_at: UtcDateTime | None


class ManualAttendanceCreate(InputModel):
    """FR-25: add an attendance entry manually (HR / manager), with a mandatory reason."""

    employee_id: int
    work_date: dt.date
    check_in_at: AwareInput | None = None
    check_out_at: AwareInput | None = None
    status: AttendanceStatus | None = None
    reason: str = Field(min_length=5, max_length=1000)

    @model_validator(mode="after")
    def _something_to_record(self) -> Self:
        if self.check_in_at is None and self.check_out_at is None and self.status is None:
            raise ValueError("provide a check-in, a check-out or a status")
        if self.check_in_at and self.check_out_at and self.check_out_at <= self.check_in_at:
            raise ValueError("check-out must be after check-in")
        return self


class CorrectionCreate(InputModel):
    field: CorrectionField
    # ISO 8601 with timezone for check_in_at / check_out_at; a status value for `status`.
    new_value: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=5, max_length=1000)


class CorrectionDecision(InputModel):
    comment: str | None = Field(default=None, max_length=1000)


class CorrectionOut(ApiModel):
    id: int
    attendance_day_id: int
    employee_id: int
    employee_code: str
    employee_name: str
    work_date: dt.date
    field: CorrectionField
    old_value: str | None
    new_value: str
    reason: str
    status: CorrectionStatus
    requested_by: int
    requested_by_name: str | None
    approved_by: int | None
    approved_by_name: str | None
    approved_at: UtcDateTime | None
    review_comment: str | None
    created_at: UtcDateTime


class CorrectionResult(ApiModel):
    correction: CorrectionOut
    attendance: AttendanceDayOut
