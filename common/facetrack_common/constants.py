"""Shared enums and contract names used by both the engine and the backend.

Values here are part of stored data and API contracts: never rename a value, only add new ones.
Tunable numbers (thresholds, FPS, cooldowns) are NOT constants — they live in `settings_keys.py`
defaults and the `settings` table.
"""

from enum import IntEnum, StrEnum


class UserRole(StrEnum):
    """The five roles of requirements §4."""

    SUPER_ADMIN = "super_admin"
    HR_ADMIN = "hr_admin"
    DEPARTMENT_MANAGER = "department_manager"
    OPERATOR = "operator"  # Security / IT Operator
    EMPLOYEE = "employee"


class AuthProvider(StrEnum):
    LOCAL = "local"
    LDAP = "ldap"


class CameraRole(StrEnum):
    """FR-1 camera roles."""

    ENTRY = "ENTRY"
    EXIT = "EXIT"
    ENTRY_EXIT = "ENTRY_EXIT"
    GENERAL = "GENERAL"


# Entrance cameras always have scheduling priority over GENERAL cameras (standards/17 §7).
ENTRANCE_CAMERA_ROLES: frozenset[CameraRole] = frozenset(
    {CameraRole.ENTRY, CameraRole.EXIT, CameraRole.ENTRY_EXIT}
)


class CameraMode(StrEnum):
    """Per-camera processing mode (requirements §10.4)."""

    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    COOLDOWN = "COOLDOWN"
    PAUSED = "PAUSED"


class CameraStatus(StrEnum):
    """Connection health of a camera as last reported by its engine node (FR-3)."""

    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    DISABLED = "disabled"


class EmployeeStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class AttendanceStatus(StrEnum):
    """FR-22 daily statuses."""

    PRESENT = "present"
    LATE = "late"
    EARLY_EXIT = "early_exit"
    HALF_DAY = "half_day"
    ABSENT = "absent"
    ON_LEAVE = "on_leave"
    HOLIDAY = "holiday"
    WEEKLY_OFF = "weekly_off"
    MISSING_CHECKOUT = "missing_checkout"


# Monthly register letters (requirements §13 screen 8; EE and HD added, see docs/open-questions.md Q31).
ATTENDANCE_STATUS_LETTERS: dict[AttendanceStatus, str] = {
    AttendanceStatus.PRESENT: "P",
    AttendanceStatus.LATE: "L",
    AttendanceStatus.ABSENT: "A",
    AttendanceStatus.HOLIDAY: "H",
    AttendanceStatus.WEEKLY_OFF: "WO",
    AttendanceStatus.ON_LEAVE: "LV",
    AttendanceStatus.MISSING_CHECKOUT: "MC",
    AttendanceStatus.EARLY_EXIT: "EE",
    AttendanceStatus.HALF_DAY: "HD",
}


class RecognitionStatus(StrEnum):
    """Status of a stored recognition event (§11). The engine only emits RECOGNIZED or UNKNOWN."""

    RECOGNIZED = "recognized"
    UNKNOWN = "unknown"
    VOIDED = "voided"


class ReviewStatus(StrEnum):
    """Review state of an unknown face (FR-27)."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    DISMISSED = "dismissed"


class CorrectionStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CorrectionField(StrEnum):
    """Attendance fields that a correction may change (FR-25)."""

    CHECK_IN_AT = "check_in_at"
    CHECK_OUT_AT = "check_out_at"
    STATUS = "status"


class EnrollmentSource(StrEnum):
    UPLOAD = "upload"
    WEBCAM = "webcam"
    REVIEW = "review"


class LeaveSource(StrEnum):
    HR = "hr"
    MANUAL = "manual"


class LoadLevel(IntEnum):
    """Degradation ladder steps (requirements §10.4)."""

    NORMAL = 1
    GENERAL_HALF_RATE = 2
    GENERAL_PAUSED = 3
    ENTRANCE_REDUCED = 4
    EMBEDDING_DEFERRED = 5


class WsMessageType(StrEnum):
    """Allowed `/ws/live` message types (standards/04). Adding one is a contract change."""

    RECOGNITION_CREATED = "RecognitionCreated"
    ATTENDANCE_UPDATED = "AttendanceUpdated"
    CAMERA_STATUS_CHANGED = "CameraStatusChanged"
    LOAD_LEVEL_CHANGED = "LoadLevelChanged"


# Redis names are part of the engine <-> backend contract.
RECOGNITION_EVENTS_STREAM = "recognition.events"
RECOGNITION_EVENTS_DEAD_LETTER_STREAM = "recognition.events.dead"
LIVE_UPDATES_CHANNEL = "facetrack.live"
ENGINE_CONTROL_CHANNEL = "facetrack.engine.control"

# Associated-data labels for AES-GCM so a ciphertext cannot be moved to another purpose.
CRYPTO_PURPOSE_EMBEDDING = b"facetrack:embedding"
CRYPTO_PURPOSE_CAMERA_URL = b"facetrack:camera-url"
CRYPTO_PURPOSE_IMAGE = b"facetrack:image"
CRYPTO_PURPOSE_SETTING = b"facetrack:setting"
