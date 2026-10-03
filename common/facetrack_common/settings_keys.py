"""Names, types and default values of every key in the `settings` table (FR-38).

This is the single place where tunable defaults are written down. The seed script inserts them;
readers (engine and backend) read the table and fall back to these defaults only for keys that are
missing. Never lower recognition thresholds, margins or voting values here without explicit
approval (NFR-2, standards/17 §6).
"""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from facetrack_common.constants import CameraRole, ReportType

SettingGroup = Literal[
    "general", "recognition", "engine", "attendance", "retention", "notifications", "integration", "auth"
]

_HHMM_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class TimeWindow(BaseModel):
    """A local-time window such as an arrival peak, "08:00" to "10:30"."""

    model_config = ConfigDict(extra="forbid")
    start: str = Field(pattern=_HHMM_PATTERN)
    end: str = Field(pattern=_HHMM_PATTERN)


class ReportSchedule(BaseModel):
    """A scheduled report email (requirements §13 screen 12, FR-32)."""

    model_config = ConfigDict(extra="forbid")
    report_type: ReportType
    frequency: Literal["daily", "weekly", "monthly"]
    time: str = Field(pattern=_HHMM_PATTERN)
    recipients: list[str] = Field(min_length=1, max_length=50)
    department_id: int | None = None
    format: Literal["xlsx", "pdf"] = "xlsx"


@dataclass(frozen=True)
class SettingSpec:
    key: str
    group: SettingGroup
    default: Any
    adapter: TypeAdapter[Any]
    description: str
    # Secret values are stored encrypted and never returned in clear by the API.
    secret: bool = False

    def validate(self, value: Any) -> Any:
        return self.adapter.validate_python(value)


def _spec(
    key: str, group: SettingGroup, default: Any, type_: Any, description: str, secret: bool = False
) -> SettingSpec:
    adapter: TypeAdapter[Any] = TypeAdapter(type_)
    adapter.validate_python(default)  # a broken default must fail at import time, not in production
    return SettingSpec(key, group, default, adapter, description, secret)


_SPECS: list[SettingSpec] = [
    # --- general ---
    _spec("general.timezone", "general", "Asia/Karachi", str, "Default timezone (NFR-14)."),
    # --- recognition (engine decision, standards/17 §6; §9 starting values) ---
    _spec(
        "recognition.match_thresholds",
        "recognition",
        {"sface": 0.36, "arcface_r50": 0.45},
        dict[str, float],
        "Default cosine match threshold per embedder model (§9). A camera's own threshold overrides it.",
    ),
    _spec("recognition.margin", "recognition", 0.08, float, "Best minus second-best employee score (§9)."),
    _spec("recognition.best_crops", "recognition", 3, int, "Best crops kept and embedded per track (§10.1)."),
    _spec("recognition.min_votes", "recognition", 2, int, "Crops that must match the same employee (§10.1)."),
    _spec("recognition.detector_min_score", "recognition", 0.6, float, "Drop faces below this score."),
    _spec("recognition.min_face_width_px", "recognition", 60, int, "Drop faces narrower than this."),
    _spec("recognition.min_crop_quality", "recognition", 0.35, float, "Quality gate for track crops."),
    _spec("recognition.min_blur_variance", "recognition", 40.0, float, "Laplacian variance gate."),
    _spec("recognition.embed_after_s", "recognition", 2.0, float, "Embed a track after this time (§10.1)."),
    _spec("recognition.track_lost_s", "recognition", 2.0, float, "A track ends after this long unseen."),
    _spec(
        "recognition.liveness_spoof_threshold",
        "recognition",
        0.5,
        float,
        "Reject a confirmed track when spoof score (1 - P(real)) is above this (FR-18).",
    ),
    _spec(
        "recognition.duplicate_warning_similarity",
        "recognition",
        0.6,
        float,
        "Warn when a new enrollment is this similar to another employee (FR-10).",
    ),
    _spec("enrollment.min_face_width_px", "recognition", 112, int, "FR-9 minimum face width."),
    _spec("enrollment.min_quality", "recognition", 0.5, float, "FR-9 minimum quality score."),
    _spec("enrollment.min_blur_variance", "recognition", 60.0, float, "FR-9 blur gate."),
    _spec("enrollment.min_photos", "recognition", 3, int, "FR-8 minimum enrollment photos."),
    _spec("enrollment.max_photos", "recognition", 10, int, "FR-8 maximum enrollment photos."),
    # --- engine scheduling (requirements §10.4, standards/17) ---
    _spec("engine.entrance_fps", "engine", 4.0, float, "ACTIVE detection rate for entrance cameras."),
    _spec("engine.general_fps", "engine", 1.0, float, "ACTIVE detection rate for general cameras."),
    _spec("engine.cooldown_fps", "engine", 1.0, float, "Detection rate in COOLDOWN."),
    _spec("engine.cooldown_enter_s", "engine", 3.0, float, "No face and no motion -> COOLDOWN."),
    _spec("engine.cooldown_idle_s", "engine", 10.0, float, "COOLDOWN -> IDLE after this much more."),
    _spec("engine.motion_min_area_ratio", "engine", 0.01, float, "Fraction of ROI pixels that must move."),
    _spec(
        "engine.peak_windows",
        "engine",
        [{"start": "08:00", "end": "10:30"}, {"start": "17:00", "end": "19:30"}],
        list[TimeWindow],
        "Arrival/departure windows: entrance cameras ACTIVE-ready, general cameras at reduced rate.",
    ),
    _spec("engine.ladder_sample_s", "engine", 5.0, float, "Load monitor sampling interval."),
    _spec("engine.ladder_cpu_high_pct", "engine", 85.0, float, "Step down above this CPU %."),
    _spec("engine.ladder_cpu_high_s", "engine", 30.0, float, "...sustained for this long."),
    _spec("engine.ladder_lag_high_s", "engine", 2.0, float, "Step down when camera lag exceeds this."),
    _spec("engine.ladder_cpu_low_pct", "engine", 60.0, float, "Step up below this CPU %."),
    _spec("engine.ladder_cpu_low_s", "engine", 120.0, float, "...sustained for this long."),
    # --- attendance rules (requirements §10.3) ---
    _spec("attendance.day_close_time", "attendance", "02:00", str, "Day-shift work day closes at (Q10)."),
    _spec(
        "attendance.night_shift_close_offset_min",
        "attendance",
        240,
        int,
        "Night-shift day closes this long after shift end (§10.3).",
    ),
    _spec(
        "attendance.duplicate_cooldown_min",
        "attendance",
        5,
        int,
        "Ignore repeat events of the same employee on the same camera within this window.",
    ),
    _spec(
        "attendance.checkin_camera_roles",
        "attendance",
        [CameraRole.ENTRY.value, CameraRole.ENTRY_EXIT.value, CameraRole.GENERAL.value],
        list[CameraRole],
        "Camera roles whose first sighting counts as check-in.",
    ),
    _spec(
        "attendance.checkout_camera_roles",
        "attendance",
        [CameraRole.EXIT.value, CameraRole.ENTRY_EXIT.value],
        list[CameraRole],
        "Camera roles whose last sighting counts as check-out (any camera if none exist).",
    ),
    _spec("attendance.overtime_enabled", "attendance", True, bool, "Compute overtime minutes."),
    _spec(
        "attendance.overtime_threshold_min", "attendance", 30, int, "Overtime starts after shift end + this."
    ),
    # --- retention (FR-39, §15) ---
    _spec("retention.snapshot_days", "retention", 90, int, "Event snapshots are deleted after this."),
    _spec("retention.unknown_face_days", "retention", 90, int, "Unknown faces are deleted after this."),
    _spec(
        "retention.enrollment_after_exit_days",
        "retention",
        30,
        int,
        "Enrollment data is erased this long after an employee is deactivated.",
    ),
    # --- notifications (FR-32, FR-33) ---
    _spec("notifications.daily_summary_enabled", "notifications", False, bool, "Email the daily summary."),
    _spec("notifications.daily_summary_time", "notifications", "10:45", str, "Local time of the summary."),
    _spec("notifications.hr_emails", "notifications", [], list[str], "HR recipients of the daily summary."),
    _spec("notifications.alert_emails", "notifications", [], list[str], "Admins alerted on failures."),
    _spec("notifications.camera_offline_alert_min", "notifications", 5, int, "FR-4 offline alert delay."),
    _spec(
        "notifications.teams_webhook_url",
        "notifications",
        "",
        str,
        "Microsoft Teams incoming webhook for alerts.",
        secret=True,
    ),
    _spec("notifications.checkin_confirmation", "notifications", False, bool, "FR-33 check-in email."),
    _spec("notifications.report_schedules", "notifications", [], list[ReportSchedule], "Scheduled reports."),
    # --- integration (FR-12, FR-24, FR-34, FR-35) ---
    _spec("integration.payroll_mode", "integration", "pull", Literal["pull", "push"], "FR-35 delivery mode."),
    _spec("integration.payroll_webhook_url", "integration", "", str, "Payroll webhook URL.", secret=True),
    _spec("integration.payroll_push_time", "integration", "03:00", str, "Local time of the daily push."),
    _spec("integration.hr_sync_enabled", "integration", False, bool, "FR-12 employee master sync."),
    _spec("integration.hr_sync_time", "integration", "01:00", str, "Local time of the nightly HR sync."),
    _spec("integration.hr_base_url", "integration", "", str, "HR system API base URL."),
    # --- auth (§15) ---
    _spec("auth.ldap_enabled", "auth", False, bool, "FR-40 Active Directory login."),
    _spec("auth.lockout_minutes", "auth", 30, int, "Lock duration after 5 failed logins (Q17)."),
]

SETTINGS: dict[str, SettingSpec] = {spec.key: spec for spec in _SPECS}


def default_settings() -> dict[str, Any]:
    """All keys with their default values, e.g. for seeding the `settings` table."""
    return {spec.key: spec.default for spec in _SPECS}


def resolve_settings(stored: dict[str, Any]) -> dict[str, Any]:
    """Merges stored values over defaults, ignoring unknown keys."""
    merged = default_settings()
    merged.update({k: v for k, v in stored.items() if k in SETTINGS})
    return merged
