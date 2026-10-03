"""SQLAlchemy 2.0 models — the sixteen tables of requirements §11."""

from facetrack_common.models.attendance import AttendanceCorrection, AttendanceDay
from facetrack_common.models.auth import ApiClient, User
from facetrack_common.models.base import Base
from facetrack_common.models.camera import Camera
from facetrack_common.models.employee import Employee, FaceEnrollment, Leave
from facetrack_common.models.organization import Department, Holiday, Location, Shift
from facetrack_common.models.recognition import RecognitionEventRecord, UnknownFace
from facetrack_common.models.system import AuditLog, Setting

__all__ = [
    "ApiClient",
    "AttendanceCorrection",
    "AttendanceDay",
    "AuditLog",
    "Base",
    "Camera",
    "Department",
    "Employee",
    "FaceEnrollment",
    "Holiday",
    "Leave",
    "Location",
    "RecognitionEventRecord",
    "Setting",
    "Shift",
    "UnknownFace",
    "User",
]
