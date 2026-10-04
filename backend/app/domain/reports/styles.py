"""Colours for Excel and PDF exports (FR-31, §13): the portal's status tones, so a file reads like the screen.

Status is always colour plus text, never colour alone (§13). The tone names and which status gets which
tone mirror `frontend/src/lib/labels.ts`; keep the two in step. The fills are Excel's familiar
"Good / Neutral / Bad" pairs, which keep dark text readable when printed.
"""

from facetrack_common.constants import AttendanceStatus

from app.schemas.report import Tone

# tone -> (fill, text colour)
TONE_COLOURS: dict[str, tuple[str, str]] = {
    "ok": ("#C6EFCE", "#006100"),  # green: present, recognised, online, approved
    "warn": ("#FFEB9C", "#7A4F00"),  # yellow: late, unknown, pending
    "bad": ("#FFC7CE", "#9C0006"),  # red: absent, missing check-out, offline, rejected
    "info": ("#DDEBF7", "#1F4E78"),  # blue
    "leave": ("#E4DFEC", "#5B2C6F"),  # purple: on leave
    "neutral": ("#EDEDED", "#3A3A3A"),  # grey: holiday, weekly off, voided, dismissed
}

BRAND = "#1F4E8C"  # portal primary (frontend/src/index.css --primary)
HEADER_TEXT = "#FFFFFF"
META_FILL = "#EEF2F8"
ZEBRA_FILL = "#F7F9FC"
BORDER = "#C9D3E0"

ATTENDANCE_STATUS_TONES: dict[AttendanceStatus, Tone] = {
    AttendanceStatus.PRESENT: "ok",
    AttendanceStatus.LATE: "warn",
    AttendanceStatus.EARLY_EXIT: "warn",
    AttendanceStatus.HALF_DAY: "warn",
    AttendanceStatus.ABSENT: "bad",
    AttendanceStatus.ON_LEAVE: "leave",
    AttendanceStatus.HOLIDAY: "neutral",
    AttendanceStatus.WEEKLY_OFF: "neutral",
    AttendanceStatus.MISSING_CHECKOUT: "bad",
}

# Monthly register letters (Q31).
LETTER_TONES: dict[str, Tone] = {
    "P": "ok",
    "L": "warn",
    "EE": "warn",
    "HD": "warn",
    "A": "bad",
    "MC": "bad",
    "LV": "leave",
    "H": "neutral",
    "WO": "neutral",
}

# Shown on every Summary sheet so a printed file can be read without the portal.
LEGEND: list[tuple[str, Tone]] = [
    ("Present / Recognised / Online / Approved", "ok"),
    ("Late / Early exit / Half day / Unknown / Pending", "warn"),
    ("Absent / Missing check-out / Offline / Rejected", "bad"),
    ("On leave", "leave"),
    ("Holiday / Weekly off / Voided / Dismissed", "neutral"),
]


def status_tone(value: object) -> Tone | None:
    try:
        return ATTENDANCE_STATUS_TONES[AttendanceStatus(str(value))]
    except ValueError:
        return None
