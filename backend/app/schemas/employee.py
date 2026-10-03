"""Employees, face enrollment and leave (FR-7..FR-13, FR-24)."""

import datetime as dt
from typing import Literal

from facetrack_common.constants import EmployeeStatus, EnrollmentSource, LeaveSource
from pydantic import EmailStr, Field, model_validator

from app.schemas.common import ApiModel, AwareInput, InputModel, UtcDateTime

_CODE = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"


class EmployeeCreate(InputModel):
    employee_code: str = Field(min_length=1, max_length=64, pattern=_CODE)
    full_name: str = Field(min_length=1, max_length=200)
    department_id: int | None = None
    designation: str | None = Field(default=None, max_length=120)
    shift_id: int | None = None
    location_id: int | None = None
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    status: EmployeeStatus = EmployeeStatus.ACTIVE
    consent_signed_at: AwareInput | None = None
    hr_external_id: str | None = Field(default=None, max_length=64)


class EmployeeUpdate(InputModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    department_id: int | None = None
    designation: str | None = Field(default=None, max_length=120)
    shift_id: int | None = None
    location_id: int | None = None
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    status: EmployeeStatus | None = None
    consent_signed_at: AwareInput | None = None
    hr_external_id: str | None = Field(default=None, max_length=64)


class EmployeeOut(ApiModel):
    id: int
    employee_code: str
    full_name: str
    department_id: int | None
    department_name: str | None = None
    designation: str | None
    shift_id: int | None
    shift_name: str | None = None
    location_id: int | None
    location_name: str | None = None
    email: str | None
    phone: str | None
    status: EmployeeStatus
    consent_signed_at: UtcDateTime | None
    deactivated_at: UtcDateTime | None
    hr_external_id: str | None
    enrolled_photos: int = 0
    enrollment_complete: bool = False
    created_at: UtcDateTime


class FaceOut(ApiModel):
    id: int
    quality_score: float
    source: EnrollmentSource
    model_name: str
    is_active: bool
    created_at: UtcDateTime


class PhotoResult(ApiModel):
    filename: str
    accepted: bool
    rejection_reason: str | None = None
    face_id: int | None = None
    quality_score: float | None = None
    face_width_px: int | None = None
    # FR-10: other employees whose enrolled faces are very similar (possible duplicate person).
    possible_duplicates: list[str] = Field(default_factory=list)


class EnrollmentResult(ApiModel):
    results: list[PhotoResult]
    enrolled_photos: int
    enrollment_complete: bool


class BiometricErasure(InputModel):
    """Erasure must be confirmed by typing the employee code (requirements §13)."""

    confirm_employee_code: str = Field(min_length=1, max_length=64)


class ImportAccepted(ApiModel):
    job_id: str


class LeaveCreate(InputModel):
    employee_id: int
    from_date: dt.date
    to_date: dt.date
    type: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _range(self) -> "LeaveCreate":
        if self.to_date < self.from_date:
            raise ValueError("to_date must not be before from_date")
        return self


class LeaveOut(ApiModel):
    id: int
    employee_id: int
    from_date: dt.date
    to_date: dt.date
    type: str
    source: LeaveSource
    external_ref: str | None
    created_at: UtcDateTime


EnrollmentSourceInput = Literal["upload", "webcam"]
