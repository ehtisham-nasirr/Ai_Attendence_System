"""Operating hours and arrival/departure peak windows, in the location's local time (§10.4)."""

from datetime import datetime, time
from typing import Any


def _parse(hhmm: str) -> time:
    hours, minutes = hhmm.split(":")
    return time(int(hours), int(minutes))


def _in_window(now_local: datetime, start: str, end: str) -> bool:
    current, begin, finish = now_local.time(), _parse(start), _parse(end)
    if begin <= finish:
        return begin <= current < finish
    return current >= begin or current < finish  # window crosses midnight


def within_operating_hours(windows: list[dict[str, Any]] | None, now_local: datetime) -> bool:
    """True when `now_local` falls in any window; no windows means always on.

    Window: {"days": [1..7] (ISO weekday, optional = every day), "start": "HH:MM", "end": "HH:MM"}.
    """
    if not windows:
        return True
    weekday = now_local.isoweekday()
    for window in windows:
        days = window.get("days")
        if days and weekday not in days:
            continue
        if _in_window(now_local, str(window["start"]), str(window["end"])):
            return True
    return False


def within_peak(peak_windows: list[dict[str, Any]], now_local: datetime) -> bool:
    return any(_in_window(now_local, str(w["start"]), str(w["end"])) for w in peak_windows)
