"""Recognition events and unknown faces (FR-16, FR-17, FR-27, FR-28)."""

from typing import Literal

from facetrack_common.constants import RecognitionStatus, ReviewStatus
from pydantic import Field

from app.schemas.common import ApiModel, InputModel, UtcDateTime


class EventOut(ApiModel):
    id: int
    event_uuid: str
    camera_id: int
    camera_name: str | None = None
    employee_id: int | None
    employee_code: str | None = None
    employee_name: str | None = None
    status: RecognitionStatus
    confidence: float
    liveness_score: float | None
    track_id: int
    captured_at: UtcDateTime
    snapshot_available: bool
    model_name: str
    void_reason: str | None
    voided_at: UtcDateTime | None


class EventVoid(InputModel):
    reason: str = Field(min_length=3, max_length=500)


class UnknownFaceOut(ApiModel):
    id: int
    recognition_event_id: int
    captured_at: UtcDateTime
    camera_id: int
    camera_name: str | None = None
    liveness_score: float | None
    review_status: ReviewStatus
    assigned_employee_id: int | None
    reviewed_at: UtcDateTime | None
    snapshot_available: bool
    # Faces with the same group id look like the same person (§13 screen 9 "grouped by similarity").
    group_id: int | None = None


class UnknownFaceAssign(InputModel):
    employee_id: int
    add_to_gallery: bool = False


class UnknownFaceAssignResult(ApiModel):
    unknown_face: UnknownFaceOut
    attendance_updated: bool
    added_to_gallery: bool
    gallery_rejection_reason: str | None = None


class UnknownFaceUpdate(InputModel):
    review_status: Literal["dismissed"]
