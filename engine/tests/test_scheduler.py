"""Camera modes, degradation ladder, rate plans and operating hours (§10.4, NFR-15, standards/17)."""

from datetime import datetime

import pytest
from facetrack_common.constants import CameraMode, CameraRole, LoadLevel

from app.scheduler.ladder import DegradationLadder, LadderLimits
from app.scheduler.modes import CameraModeMachine, ModeTimings
from app.scheduler.operating_hours import within_operating_hours, within_peak
from app.scheduler.rates import RateSettings, plan_processing

TIMINGS = ModeTimings(cooldown_enter_s=3.0, cooldown_idle_s=10.0)
LIMITS = LadderLimits(cpu_high_pct=85, cpu_high_s=30, lag_high_s=2, cpu_low_pct=60, cpu_low_s=120)
RATES = RateSettings(entrance_fps=4.0, general_fps=1.0, cooldown_fps=1.0)


def test_mode_cycle_idle_active_cooldown_idle() -> None:
    machine = CameraModeMachine(TIMINGS, now=0.0)
    assert machine.update(1.0, motion=False, face=False, paused=False) == CameraMode.IDLE
    assert machine.update(2.0, motion=True, face=False, paused=False) == CameraMode.ACTIVE
    assert (
        machine.update(4.0, motion=False, face=True, paused=False) == CameraMode.ACTIVE
    )  # face keeps active
    assert machine.update(6.9, motion=False, face=False, paused=False) == CameraMode.ACTIVE
    assert machine.update(7.0, motion=False, face=False, paused=False) == CameraMode.COOLDOWN
    assert machine.update(16.9, motion=False, face=False, paused=False) == CameraMode.COOLDOWN
    assert machine.update(17.0, motion=False, face=False, paused=False) == CameraMode.IDLE


def test_cooldown_returns_to_active_on_motion() -> None:
    machine = CameraModeMachine(TIMINGS, now=0.0)
    machine.update(1.0, motion=True, face=False, paused=False)
    machine.update(4.5, motion=False, face=False, paused=False)
    assert machine.mode == CameraMode.COOLDOWN
    assert machine.update(5.0, motion=True, face=False, paused=False) == CameraMode.ACTIVE


def test_paused_and_resume_to_idle() -> None:
    machine = CameraModeMachine(TIMINGS, now=0.0)
    machine.update(1.0, motion=True, face=False, paused=False)
    assert machine.update(2.0, motion=True, face=True, paused=True) == CameraMode.PAUSED
    assert machine.update(3.0, motion=True, face=False, paused=False) == CameraMode.IDLE


def test_nfr15_ladder_steps_down_under_sustained_cpu_and_back_up() -> None:
    ladder = DegradationLadder(LIMITS, now=0.0)
    t = 0.0
    while t < 29:
        t += 5
        ladder.update(t, cpu_percent=95, max_lag_s=0.0)
    assert ladder.level == LoadLevel.NORMAL  # not yet 30 s
    levels = []
    for _ in range(40):  # force overload for 200 s
        t += 5
        levels.append(ladder.update(t, cpu_percent=95, max_lag_s=0.0))
    assert ladder.level == LoadLevel.EMBEDDING_DEFERRED
    assert levels == sorted(levels)  # one step at a time, never skipping back up
    for _ in range(23):  # 115 s of low CPU: not yet 2 minutes
        t += 5
        ladder.update(t, cpu_percent=30, max_lag_s=0.0)
    assert ladder.level == LoadLevel.EMBEDDING_DEFERRED
    for _ in range(200):
        t += 5
        ladder.update(t, cpu_percent=30, max_lag_s=0.0)
    assert ladder.level == LoadLevel.NORMAL


def test_ladder_steps_down_on_lag_but_holds_between_steps() -> None:
    ladder = DegradationLadder(LIMITS, now=0.0)
    assert ladder.update(31.0, cpu_percent=40, max_lag_s=3.0) == LoadLevel.GENERAL_HALF_RATE
    assert ladder.update(36.0, cpu_percent=40, max_lag_s=3.0) == LoadLevel.GENERAL_HALF_RATE  # held
    assert ladder.update(62.0, cpu_percent=40, max_lag_s=3.0) == LoadLevel.GENERAL_PAUSED


def test_ladder_does_not_step_up_while_lagging() -> None:
    ladder = DegradationLadder(LIMITS, now=0.0)
    ladder.update(31.0, cpu_percent=40, max_lag_s=3.0)
    t = 31.0
    for _ in range(60):
        t += 5
        ladder.update(t, cpu_percent=10, max_lag_s=2.5)
    assert ladder.level >= LoadLevel.GENERAL_HALF_RATE


@pytest.mark.parametrize(
    ("role", "level", "fps", "paused"),
    [
        (CameraRole.ENTRY, LoadLevel.NORMAL, 4.0, False),
        (CameraRole.GENERAL, LoadLevel.NORMAL, 1.0, False),
        (CameraRole.GENERAL, LoadLevel.GENERAL_HALF_RATE, 0.5, False),
        (CameraRole.GENERAL, LoadLevel.GENERAL_PAUSED, 0.0, True),
        (CameraRole.ENTRY_EXIT, LoadLevel.GENERAL_PAUSED, 4.0, False),
        (CameraRole.EXIT, LoadLevel.ENTRANCE_REDUCED, 2.0, False),
        (CameraRole.ENTRY, LoadLevel.EMBEDDING_DEFERRED, 2.0, False),
    ],
)
def test_ladder_steps_apply_per_role(role: CameraRole, level: LoadLevel, fps: float, paused: bool) -> None:
    plan = plan_processing(role, CameraMode.ACTIVE, level, None, RATES, in_peak=False)
    assert plan.detect_fps == fps
    assert plan.paused is paused


def test_steps_4_and_5_flags() -> None:
    plan4 = plan_processing(
        CameraRole.ENTRY, CameraMode.ACTIVE, LoadLevel.ENTRANCE_REDUCED, None, RATES, False
    )
    assert plan4.liveness_low_priority and not plan4.defer_embedding
    plan5 = plan_processing(
        CameraRole.ENTRY, CameraMode.ACTIVE, LoadLevel.EMBEDDING_DEFERRED, None, RATES, False
    )
    assert plan5.defer_embedding and plan5.detect_fps > 0  # detection and tracking keep running


def test_idle_is_keyframe_only_without_detection() -> None:
    plan = plan_processing(CameraRole.ENTRY, CameraMode.IDLE, LoadLevel.NORMAL, None, RATES, in_peak=False)
    assert plan.keyframes_only and plan.detect_fps == 0


def test_peak_keeps_entrance_active_ready_and_slows_general() -> None:
    entrance = plan_processing(CameraRole.ENTRY, CameraMode.IDLE, LoadLevel.NORMAL, None, RATES, in_peak=True)
    assert not entrance.keyframes_only
    general = plan_processing(
        CameraRole.GENERAL, CameraMode.ACTIVE, LoadLevel.NORMAL, None, RATES, in_peak=True
    )
    assert general.detect_fps == 0.5


def test_cooldown_detects_at_1fps_and_camera_fps_overrides_role_default() -> None:
    cool = plan_processing(CameraRole.ENTRY, CameraMode.COOLDOWN, LoadLevel.NORMAL, None, RATES, False)
    assert cool.detect_fps == 1.0
    custom = plan_processing(CameraRole.ENTRY, CameraMode.ACTIVE, LoadLevel.NORMAL, 5.0, RATES, False)
    assert custom.detect_fps == 5.0


def test_operating_hours_including_overnight_and_days() -> None:
    windows = [
        {"days": [1, 2, 3, 4, 5], "start": "07:00", "end": "21:00"},
        {"start": "22:00", "end": "06:00"},
    ]
    monday_9 = datetime(2026, 10, 5, 9, 0)
    sunday_9 = datetime(2026, 10, 4, 9, 0)
    sunday_23 = datetime(2026, 10, 4, 23, 0)
    assert within_operating_hours(windows, monday_9)
    assert not within_operating_hours(windows, sunday_9)
    assert within_operating_hours(windows, sunday_23)
    assert within_operating_hours(None, sunday_9)


def test_peak_windows() -> None:
    peaks = [{"start": "08:00", "end": "10:30"}]
    assert within_peak(peaks, datetime(2026, 10, 5, 10, 29))
    assert not within_peak(peaks, datetime(2026, 10, 5, 10, 30))
