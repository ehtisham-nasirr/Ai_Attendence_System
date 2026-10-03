"""Every attendance rule and edge case of requirements §10.3 and §17 (FR-20..FR-23)."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from facetrack_common.constants import AttendanceStatus as S
from facetrack_common.constants import CameraRole as R

from app.domain.attendance.rules import (
    DayInputs,
    RuleSettings,
    ShiftRule,
    Sighting,
    compute_day,
    day_close_at,
    derive_times,
    shift_bounds,
    work_date_for,
)

PKT = ZoneInfo("Asia/Karachi")
DAY = ShiftRule(time(9), time(18), 15, 15, 50, False, frozenset({6, 7}))
NIGHT = ShiftRule(time(22), time(6), 15, 15, 50, True, frozenset())
SETTINGS = RuleSettings(
    day_close_time=time(2),
    night_shift_close_offset_min=240,
    duplicate_cooldown_min=5,
    checkin_roles=frozenset({R.ENTRY, R.ENTRY_EXIT, R.GENERAL}),
    checkout_roles=frozenset({R.EXIT, R.ENTRY_EXIT}),
    overtime_enabled=True,
    overtime_threshold_min=30,
)
MONDAY = date(2026, 10, 5)


def at(day: date, hh: int, mm: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=PKT)


def day_result(check_in: datetime | None, check_out: datetime | None, finalize: bool = True, **kw: object):  # type: ignore[no-untyped-def]
    inputs = DayInputs(
        work_date=kw.pop("work_date", MONDAY),  # type: ignore[arg-type]
        shift=kw.pop("shift", DAY),  # type: ignore[arg-type]
        tz=PKT,
        check_in=check_in,
        check_out=check_out,
        on_leave=bool(kw.pop("on_leave", False)),
        holiday=bool(kw.pop("holiday", False)),
        manual_status=kw.pop("manual_status", None),  # type: ignore[arg-type]
    )
    return compute_day(inputs, SETTINGS, finalize)


def test_fr22_on_time_is_present() -> None:
    result = day_result(at(MONDAY, 9, 10), at(MONDAY, 18, 5))
    assert result.status == S.PRESENT and result.late_minutes == 0 and result.worked_minutes == 535


def test_fr22_late_after_grace_period() -> None:
    assert day_result(at(MONDAY, 9, 15), at(MONDAY, 18)).status == S.PRESENT  # exactly at grace
    late = day_result(at(MONDAY, 9, 40), at(MONDAY, 18))
    assert late.status == S.LATE and late.late_minutes == 25  # counted beyond start + grace


def test_fr22_early_exit_before_shift_end_minus_grace() -> None:
    assert day_result(at(MONDAY, 9), at(MONDAY, 17, 45)).status == S.PRESENT
    early = day_result(at(MONDAY, 9), at(MONDAY, 17, 0))
    assert early.status == S.EARLY_EXIT and early.early_minutes == 45


def test_fr22_half_day_below_half_of_shift_hours() -> None:
    result = day_result(at(MONDAY, 9), at(MONDAY, 13, 29))  # 269 min < 50% of 540
    assert result.status == S.HALF_DAY
    assert day_result(at(MONDAY, 9), at(MONDAY, 13, 30)).status == S.EARLY_EXIT  # exactly 50%: not half day


def test_adr0003_precedence_half_day_over_late_over_early() -> None:
    assert day_result(at(MONDAY, 12), at(MONDAY, 14)).status == S.HALF_DAY  # late + half day
    both = day_result(at(MONDAY, 9, 40), at(MONDAY, 17))  # late + early exit
    assert both.status == S.LATE and both.late_minutes == 25 and both.early_minutes == 45


def test_fr23_missing_checkout_beats_everything_automatic() -> None:
    assert day_result(at(MONDAY, 11), None).status == S.MISSING_CHECKOUT


def test_q12_provisional_status_before_close_is_present_or_late() -> None:
    assert day_result(at(MONDAY, 9), None, finalize=False).status == S.PRESENT
    assert day_result(at(MONDAY, 10), at(MONDAY, 11), finalize=False).status == S.LATE
    assert day_result(None, None, finalize=False).status is None


def test_fr23_absent_on_working_day_without_recognition() -> None:
    assert day_result(None, None).status == S.ABSENT


def test_overtime_beyond_shift_end_plus_threshold() -> None:
    assert day_result(at(MONDAY, 9), at(MONDAY, 18, 30)).overtime_minutes == 0
    assert day_result(at(MONDAY, 9), at(MONDAY, 19, 45)).overtime_minutes == 75


def test_overtime_can_be_switched_off() -> None:
    settings = RuleSettings(time(2), 240, 5, SETTINGS.checkin_roles, SETTINGS.checkout_roles, False, 30)
    inputs = DayInputs(MONDAY, DAY, PKT, at(MONDAY, 9), at(MONDAY, 21), False, False)
    assert compute_day(inputs, settings, True).overtime_minutes == 0


def test_fr21_weekly_off_and_holiday_and_leave() -> None:
    saturday = date(2026, 10, 10)
    assert day_result(None, None, work_date=saturday).status == S.WEEKLY_OFF
    assert day_result(None, None, holiday=True).status == S.HOLIDAY
    assert day_result(None, None, on_leave=True).status == S.ON_LEAVE


def test_section_10_3_precedence_leave_over_holiday_over_automatic() -> None:
    assert day_result(None, None, holiday=True, on_leave=True).status == S.ON_LEAVE
    worked_holiday = day_result(at(MONDAY, 10), at(MONDAY, 20), holiday=True)
    assert (
        worked_holiday.status == S.HOLIDAY and worked_holiday.late_minutes == 0
    )  # Q15: no lateness off-duty
    assert worked_holiday.worked_minutes == 600 and worked_holiday.overtime_minutes == 90


def test_section_10_3_manual_correction_wins() -> None:
    assert day_result(None, None, on_leave=True, manual_status=S.PRESENT).status == S.PRESENT


def test_q13_seen_only_on_exit_camera_is_present() -> None:
    assert day_result(None, at(MONDAY, 18)).status == S.PRESENT


def test_q35_no_shift_is_never_marked_absent() -> None:
    assert day_result(None, None, shift=None).status is None
    no_shift = day_result(at(MONDAY, 11), at(MONDAY, 12), shift=None)
    assert no_shift.status == S.PRESENT and no_shift.late_minutes == 0


# --- night shift / work date (FR-21, §10.3 "Night shift: attendance day = shift start date") ---


def test_fr21_night_shift_bounds_cross_midnight() -> None:
    start, end = shift_bounds(MONDAY, NIGHT, PKT)
    assert start == at(MONDAY, 22) and end == at(MONDAY + timedelta(days=1), 6)


def test_fr21_night_shift_events_after_midnight_belong_to_start_date() -> None:
    tuesday = MONDAY + timedelta(days=1)
    assert work_date_for(at(MONDAY, 21, 50), NIGHT, PKT, SETTINGS) == MONDAY
    assert work_date_for(at(tuesday, 5, 59), NIGHT, PKT, SETTINGS) == MONDAY
    assert work_date_for(at(tuesday, 9, 59), NIGHT, PKT, SETTINGS) == MONDAY  # before close (06:00 + 4 h)
    assert work_date_for(at(tuesday, 10, 1), NIGHT, PKT, SETTINGS) == tuesday


def test_fr21_night_shift_day_computation() -> None:
    tuesday = MONDAY + timedelta(days=1)
    result = day_result(at(MONDAY, 22, 5), at(tuesday, 6, 10), shift=NIGHT)
    assert result.status == S.PRESENT and result.worked_minutes == 485
    late = day_result(at(MONDAY, 22, 30), at(tuesday, 6), shift=NIGHT)
    assert late.status == S.LATE and late.late_minutes == 15


def test_q10_day_shift_work_date_closes_at_0200_next_day() -> None:
    tuesday = MONDAY + timedelta(days=1)
    assert day_close_at(MONDAY, DAY, PKT, SETTINGS) == at(tuesday, 2)
    assert work_date_for(at(tuesday, 1, 30), DAY, PKT, SETTINGS) == MONDAY  # late overtime check-out
    assert work_date_for(at(tuesday, 2, 1), DAY, PKT, SETTINGS) == tuesday
    assert (
        work_date_for(at(tuesday, 2, 0).astimezone(UTC), DAY, PKT, SETTINGS) == MONDAY
    )  # boundary inclusive


# --- check-in / check-out derivation and duplicate suppression ---


def s(event_id: int, hh: int, mm: int, role: R, camera_id: int = 1) -> Sighting:
    return Sighting(event_id, at(MONDAY, hh, mm), camera_id, role)


def test_check_in_first_entry_check_out_last_exit_order_independent() -> None:
    sightings = [
        s(3, 18, 5, R.EXIT, 2),
        s(1, 9, 2, R.ENTRY),
        s(2, 13, 0, R.GENERAL, 3),
        s(4, 17, 0, R.EXIT, 2),
    ]
    check_in, check_out = derive_times(sightings, SETTINGS, location_has_exit_cameras=True)
    assert check_in is not None and check_in.event_id == 1
    assert check_out is not None and check_out.event_id == 3
    reversed_in, reversed_out = derive_times(list(reversed(sightings)), SETTINGS, True)
    assert (reversed_in, reversed_out) == (check_in, check_out)


def test_general_camera_never_gives_check_out_when_exit_cameras_exist() -> None:
    _, check_out = derive_times([s(1, 9, 0, R.ENTRY), s(2, 18, 0, R.GENERAL, 3)], SETTINGS, True)
    assert check_out is None


def test_without_exit_cameras_last_sighting_on_any_camera_is_check_out() -> None:
    _, check_out = derive_times([s(1, 9, 0, R.ENTRY), s(2, 18, 0, R.GENERAL, 3)], SETTINGS, False)
    assert check_out is not None and check_out.event_id == 2


def test_q14_single_sighting_on_entry_exit_camera_has_no_check_out() -> None:
    check_in, check_out = derive_times([s(1, 9, 0, R.ENTRY_EXIT)], SETTINGS, True)
    assert check_in is not None and check_out is None


def test_duplicate_suppression_same_camera_within_cooldown() -> None:
    sightings = [s(1, 9, 0, R.ENTRY_EXIT), s(2, 9, 4, R.ENTRY_EXIT), s(3, 9, 6, R.ENTRY_EXIT)]
    check_in, check_out = derive_times(sightings, SETTINGS, True)
    assert check_in is not None and check_in.event_id == 1
    assert check_out is not None and check_out.event_id == 3  # event 2 ignored as a repeat


def test_duplicate_suppression_is_per_camera() -> None:
    _, check_out = derive_times([s(1, 9, 0, R.ENTRY, 1), s(2, 9, 2, R.EXIT, 2)], SETTINGS, True)
    assert check_out is not None and check_out.event_id == 2


def test_exit_only_sightings() -> None:
    check_in, check_out = derive_times([s(1, 18, 0, R.EXIT, 2)], SETTINGS, True)
    assert check_in is None and check_out is not None


@pytest.mark.parametrize("roles", [frozenset({R.ENTRY}), frozenset({R.ENTRY, R.ENTRY_EXIT})])
def test_configurable_check_in_roles(roles: frozenset[R]) -> None:
    settings = RuleSettings(time(2), 240, 5, roles, SETTINGS.checkout_roles, True, 30)
    check_in, _ = derive_times([s(1, 8, 0, R.GENERAL, 3), s(2, 9, 0, R.ENTRY)], settings, True)
    assert check_in is not None and check_in.event_id == 2
