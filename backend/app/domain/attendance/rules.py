"""Attendance rules (requirements §10.3, FR-20..FR-23) — the ONLY implementation (standards/15).

Pure functions: no database, no I/O. All instants are timezone-aware; they are stored in UTC and
converted to the location timezone only to find business dates (NFR-14).

Decisions recorded in docs/open-questions.md and ADRs:
- Work-date boundaries (Q10): day shifts close at `day_close_time` (default 02:00 next day);
  night shifts close at shift end + `night_shift_close_offset_min`. An instant t belongs to work date D
  when close(D-1) < t <= close(D). Night shift attendance therefore lands on the shift start date.
- Status precedence (ADR-0003): manual correction > leave > holiday/weekly off > automatic, and among
  automatic final statuses: Missing Check-out > Half Day > Late > Early Exit > Present.
- Provisional statuses before day close (Q12): only Present / Late.
- Overtime (Q11): check-out - (shift end + threshold), when positive.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from facetrack_common.constants import AttendanceStatus, CameraRole


@dataclass(frozen=True, slots=True)
class ShiftRule:
    start_time: time
    end_time: time
    grace_in_min: int
    grace_out_min: int
    half_day_pct: int
    is_night_shift: bool
    weekly_offs: frozenset[int]  # ISO weekdays, 1 = Monday


@dataclass(frozen=True, slots=True)
class RuleSettings:
    day_close_time: time
    night_shift_close_offset_min: int
    duplicate_cooldown_min: int
    checkin_roles: frozenset[CameraRole]
    checkout_roles: frozenset[CameraRole]
    overtime_enabled: bool
    overtime_threshold_min: int


@dataclass(frozen=True, slots=True)
class DayInputs:
    work_date: date
    shift: ShiftRule | None
    tz: ZoneInfo
    check_in: datetime | None
    check_out: datetime | None
    on_leave: bool
    holiday: bool
    manual_status: AttendanceStatus | None = None


@dataclass(frozen=True, slots=True)
class DayResult:
    worked_minutes: int
    late_minutes: int
    early_minutes: int
    overtime_minutes: int
    status: AttendanceStatus | None


def parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def _minutes(delta: timedelta) -> int:
    return max(0, int(delta.total_seconds() // 60))


def crosses_midnight(shift: ShiftRule) -> bool:
    return shift.is_night_shift or shift.end_time <= shift.start_time


def shift_bounds(work_date: date, shift: ShiftRule, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Scheduled start and end of the shift that begins on `work_date`, as aware datetimes."""
    start = datetime.combine(work_date, shift.start_time, tzinfo=tz)
    end_date = work_date + timedelta(days=1) if crosses_midnight(shift) else work_date
    end = datetime.combine(end_date, shift.end_time, tzinfo=tz)
    return start, end


def day_close_at(work_date: date, shift: ShiftRule | None, tz: ZoneInfo, settings: RuleSettings) -> datetime:
    """When the work day `work_date` is finalised (FR-23)."""
    if shift is not None and crosses_midnight(shift):
        _, end = shift_bounds(work_date, shift, tz)
        return end + timedelta(minutes=settings.night_shift_close_offset_min)
    return datetime.combine(work_date + timedelta(days=1), settings.day_close_time, tzinfo=tz)


def work_date_for(instant: datetime, shift: ShiftRule | None, tz: ZoneInfo, settings: RuleSettings) -> date:
    """The work date an event at `instant` belongs to: close(D-1) < instant <= close(D)."""
    local_date = instant.astimezone(tz).date()
    for candidate in (local_date - timedelta(days=1), local_date, local_date + timedelta(days=1)):
        opens = day_close_at(candidate - timedelta(days=1), shift, tz, settings)
        closes = day_close_at(candidate, shift, tz, settings)
        if opens < instant <= closes:
            return candidate
    return local_date  # unreachable for sane settings; keep the calendar date as a safe fallback


def is_weekly_off(work_date: date, shift: ShiftRule | None) -> bool:
    return shift is not None and work_date.isoweekday() in shift.weekly_offs


def compute_day(inputs: DayInputs, settings: RuleSettings, finalize: bool) -> DayResult:
    """Derived minutes and the status of one employee-day."""
    shift = inputs.shift
    check_in, check_out = inputs.check_in, inputs.check_out
    worked = _minutes(check_out - check_in) if check_in and check_out and check_out > check_in else 0
    weekly_off = is_weekly_off(inputs.work_date, shift)
    working_day = not (inputs.on_leave or inputs.holiday or weekly_off)

    late = early = overtime = 0
    half_day = False
    if shift is not None:
        start, end = shift_bounds(inputs.work_date, shift, inputs.tz)
        if working_day and check_in is not None:
            # FR-22 late after grace; minutes counted beyond start + grace (standards/10 example).
            late = _minutes(check_in - (start + timedelta(minutes=shift.grace_in_min)))
        if working_day and check_out is not None:
            early = _minutes((end - timedelta(minutes=shift.grace_out_min)) - check_out)
        if check_out is not None and settings.overtime_enabled:
            overtime = _minutes(check_out - (end + timedelta(minutes=settings.overtime_threshold_min)))
        shift_minutes = _minutes(end - start)
        half_day = (
            check_in is not None
            and check_out is not None
            and worked * 100 < shift.half_day_pct * shift_minutes
        )

    return DayResult(
        worked, late, early, overtime, _status(inputs, weekly_off, late, early, half_day, finalize)
    )


def _status(
    inputs: DayInputs, weekly_off: bool, late: int, early: int, half_day: bool, finalize: bool
) -> AttendanceStatus | None:
    if inputs.manual_status is not None:
        return inputs.manual_status
    if inputs.on_leave:
        return AttendanceStatus.ON_LEAVE
    if inputs.holiday:
        return AttendanceStatus.HOLIDAY
    if weekly_off:
        return AttendanceStatus.WEEKLY_OFF
    if inputs.check_in is None and inputs.check_out is None:
        if finalize and inputs.shift is not None:
            return AttendanceStatus.ABSENT
        return None  # not yet in, or no schedule to judge absence against (Q33)
    if inputs.check_in is None:
        return AttendanceStatus.PRESENT  # seen only on an exit camera (Q13)
    if not finalize:
        return AttendanceStatus.LATE if late > 0 else AttendanceStatus.PRESENT
    if inputs.check_out is None:
        return AttendanceStatus.MISSING_CHECKOUT
    if half_day:
        return AttendanceStatus.HALF_DAY
    if late > 0:
        return AttendanceStatus.LATE
    if early > 0:
        return AttendanceStatus.EARLY_EXIT
    return AttendanceStatus.PRESENT


@dataclass(frozen=True, slots=True)
class Sighting:
    """A recognised, non-voided event as the rules see it."""

    event_id: int
    captured_at: datetime
    camera_id: int
    camera_role: CameraRole


def is_duplicate(sighting: Sighting, previous: list[Sighting], settings: RuleSettings) -> bool:
    """§10.3: repeat events of the same employee on the same camera within the cooldown are ignored."""
    window = timedelta(minutes=settings.duplicate_cooldown_min)
    return any(
        p.camera_id == sighting.camera_id
        and p.event_id != sighting.event_id
        and timedelta(0) <= sighting.captured_at - p.captured_at < window
        for p in previous
    )


def checkout_roles(settings: RuleSettings, location_has_exit_cameras: bool) -> frozenset[CameraRole]:
    """Check-out comes from exit cameras; with none at the location, any camera counts (§10.3)."""
    return settings.checkout_roles if location_has_exit_cameras else frozenset(CameraRole)


def derive_times(
    sightings: list[Sighting], settings: RuleSettings, location_has_exit_cameras: bool
) -> tuple[Sighting | None, Sighting | None]:
    """Check-in = first sighting on a check-in camera; check-out = last later sighting on an exit camera.

    Order-independent, so replayed or late events give the same result (NFR-7).
    """
    ordered = sorted(sightings, key=lambda s: (s.captured_at, s.event_id))
    kept: list[Sighting] = []
    for sighting in ordered:
        if not is_duplicate(sighting, kept, settings):
            kept.append(sighting)
    check_in = next((s for s in kept if s.camera_role in settings.checkin_roles), None)
    exit_roles = checkout_roles(settings, location_has_exit_cameras)
    exits = [s for s in kept if s.camera_role in exit_roles]
    if check_in is not None:
        exits = [s for s in exits if s.captured_at > check_in.captured_at]
    check_out = exits[-1] if exits else None
    return check_in, check_out


def to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)
