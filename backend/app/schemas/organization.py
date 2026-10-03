"""Locations, departments, shifts and holidays (FR-21, FR-36)."""

import datetime as dt
from datetime import time
from zoneinfo import available_timezones

from pydantic import Field, field_validator

from app.schemas.common import ApiModel, InputModel, UtcDateTime


def _check_timezone(value: str) -> str:
    if value not in available_timezones():
        raise ValueError("unknown IANA timezone")
    return value


class LocationCreate(InputModel):
    name: str = Field(min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=500)
    timezone: str = "Asia/Karachi"

    _tz = field_validator("timezone")(_check_timezone)


class LocationUpdate(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=500)
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str | None) -> str | None:
        return None if value is None else _check_timezone(value)


class LocationOut(ApiModel):
    id: int
    name: str
    address: str | None
    timezone: str
    created_at: UtcDateTime


class DepartmentCreate(InputModel):
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    manager_user_id: int | None = None


class DepartmentUpdate(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    code: str | None = Field(default=None, min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    manager_user_id: int | None = None


class DepartmentOut(ApiModel):
    id: int
    name: str
    code: str
    manager_user_id: int | None
    created_at: UtcDateTime


class ShiftBase(InputModel):
    grace_in_min: int = Field(default=15, ge=0, le=240)
    grace_out_min: int = Field(default=15, ge=0, le=240)
    half_day_pct: int = Field(default=50, ge=1, le=100)
    is_night_shift: bool = False
    weekly_offs: list[int] = Field(default_factory=list, max_length=7)

    @field_validator("weekly_offs")
    @classmethod
    def _weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 1 or day > 7 for day in value):
            raise ValueError("weekly offs are ISO weekdays 1 (Monday) to 7 (Sunday)")
        return sorted(set(value))


class ShiftCreate(ShiftBase):
    name: str = Field(min_length=1, max_length=120)
    start_time: time
    end_time: time


class ShiftUpdate(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    start_time: time | None = None
    end_time: time | None = None
    grace_in_min: int | None = Field(default=None, ge=0, le=240)
    grace_out_min: int | None = Field(default=None, ge=0, le=240)
    half_day_pct: int | None = Field(default=None, ge=1, le=100)
    is_night_shift: bool | None = None
    weekly_offs: list[int] | None = None


class ShiftOut(ApiModel):
    id: int
    name: str
    start_time: time
    end_time: time
    grace_in_min: int
    grace_out_min: int
    half_day_pct: int
    is_night_shift: bool
    weekly_offs: list[int]
    created_at: UtcDateTime


class HolidayCreate(InputModel):
    location_id: int
    date: dt.date
    name: str = Field(min_length=1, max_length=120)


class HolidayUpdate(InputModel):
    date: dt.date | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)


class HolidayOut(ApiModel):
    id: int
    location_id: int
    date: dt.date
    name: str
    created_at: UtcDateTime
