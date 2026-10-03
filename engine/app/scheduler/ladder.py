"""Degradation ladder (requirements §10.4, standards/17 §7, NFR-15).

Steps down one level when CPU stays above the high mark for the configured time, or camera lag exceeds
its limit; steps up one level when CPU stays below the low mark for the configured time. After any
change the ladder holds for one high-CPU window before stepping down again, so a single spike cannot
cascade straight to the bottom.
"""

from dataclasses import dataclass

from facetrack_common.constants import LoadLevel


@dataclass(frozen=True, slots=True)
class LadderLimits:
    cpu_high_pct: float
    cpu_high_s: float
    lag_high_s: float
    cpu_low_pct: float
    cpu_low_s: float


class DegradationLadder:
    def __init__(self, limits: LadderLimits, now: float) -> None:
        self.limits = limits
        self.level = LoadLevel.NORMAL
        self.since = now
        self._high_since: float | None = None
        self._low_since: float | None = None

    def update(self, now: float, cpu_percent: float, max_lag_s: float) -> LoadLevel:
        """Feeds one load sample; returns the level after it."""
        limits = self.limits
        self._high_since = (self._high_since or now) if cpu_percent > limits.cpu_high_pct else None
        self._low_since = (self._low_since or now) if cpu_percent < limits.cpu_low_pct else None

        held_long_enough = now - self.since >= limits.cpu_high_s
        cpu_overloaded = self._high_since is not None and now - self._high_since >= limits.cpu_high_s
        lagging = max_lag_s > limits.lag_high_s
        if (cpu_overloaded or lagging) and held_long_enough and self.level < LoadLevel.EMBEDDING_DEFERRED:
            return self._move(LoadLevel(self.level + 1), now)

        recovered = self._low_since is not None and now - self._low_since >= limits.cpu_low_s
        if recovered and not lagging and self.level > LoadLevel.NORMAL:
            return self._move(LoadLevel(self.level - 1), now)
        return self.level

    def _move(self, level: LoadLevel, now: float) -> LoadLevel:
        self.level = level
        self.since = now
        # Restart both windows: the next step needs a fresh sustained period.
        self._high_since = None
        self._low_since = None
        return level
