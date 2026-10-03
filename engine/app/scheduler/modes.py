"""Per-camera mode state machine (requirements §10.4 "Camera modes", standards/17 §2).

IDLE --motion--> ACTIVE --no face & no motion for cooldown_enter_s--> COOLDOWN
COOLDOWN --motion--> ACTIVE ; COOLDOWN --cooldown_idle_s more without motion--> IDLE
any --outside operating hours or shed by the ladder--> PAUSED --back in hours and not shed--> IDLE

This is the only place that decides a camera's mode.
"""

from dataclasses import dataclass

from facetrack_common.constants import CameraMode


@dataclass(frozen=True, slots=True)
class ModeTimings:
    cooldown_enter_s: float
    cooldown_idle_s: float


class CameraModeMachine:
    def __init__(self, timings: ModeTimings, now: float) -> None:
        self._timings = timings
        self.mode = CameraMode.IDLE
        self.since = now
        self._last_activity = now  # last time motion or a face was seen

    def update(self, now: float, *, motion: bool, face: bool, paused: bool) -> CameraMode:
        """Advances the machine; returns the (possibly new) mode."""
        if paused:
            return self._enter(CameraMode.PAUSED, now)
        if self.mode == CameraMode.PAUSED:
            self._last_activity = now
            return self._enter(CameraMode.IDLE, now)

        if motion or face:
            self._last_activity = now
        quiet_for = now - self._last_activity

        if self.mode == CameraMode.IDLE:
            if motion:
                return self._enter(CameraMode.ACTIVE, now)
        elif self.mode == CameraMode.ACTIVE:
            if quiet_for >= self._timings.cooldown_enter_s:
                return self._enter(CameraMode.COOLDOWN, now)
        elif self.mode == CameraMode.COOLDOWN:
            if motion or face:
                return self._enter(CameraMode.ACTIVE, now)
            if now - self.since >= self._timings.cooldown_idle_s:
                return self._enter(CameraMode.IDLE, now)
        return self.mode

    def _enter(self, mode: CameraMode, now: float) -> CameraMode:
        if mode != self.mode:
            self.mode = mode
            self.since = now
        return self.mode
