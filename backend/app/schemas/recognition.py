"""Recognition events and unknown faces (FR-16, FR-17, FR-27, FR-28)."""

from typing import Annotated, Literal

from facetrack_common.constants import RecognitionStatus, ReviewStatus
from facetrack_common.schemas.envelope import PaginatedResponse
from pydantic import Field, model_validator

from app.schemas.common import ApiModel, InputModel, UtcDateTime

# At most this many unknown faces are grouped per request (newest first), and at most this many can be
# decided in one bulk request. Larger sets are reported as truncated, never cut silently.
UNKNOWN_GROUPING_MAX_FACES = 5000
# Sample faces returned per group card.
UNKNOWN_GROUP_SAMPLES = 8


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


class UnknownFaceGroupOut(ApiModel):
    """One card of the review screen: faces that look like the same person (§13 screen 9)."""

    # Id of the oldest face in the group; stays the same while newer faces join (Q58).
    group_id: int
    face_count: int
    pending_count: int
    first_seen_at: UtcDateTime
    last_seen_at: UtcDateTime
    # Distinct cameras, newest sighting first; `camera_names[i]` belongs to `camera_ids[i]`.
    camera_ids: list[int]
    camera_names: list[str]
    # Every face in the group, newest first (for bulk decisions).
    face_ids: list[int]
    # Up to 8 faces for the thumbnails: faces with a snapshot first, then newest first.
    samples: list[UnknownFaceOut]


class UnknownFaceGrouping(ApiModel):
    """How much of the queue the groups cover. `truncated` is true when older faces were left out."""

    faces_total: int
    faces_grouped: int
    max_faces: int
    truncated: bool


class UnknownFaceGroupsResponse(PaginatedResponse[UnknownFaceGroupOut]):
    """The standard list envelope (standards/04) plus `grouping`, so a cut-off is never silent."""

    grouping: UnknownFaceGrouping


class UnknownFaceBulkAction(InputModel):
    """One decision for many faces (a whole group): assign to an employee or dismiss (FR-27)."""

    face_ids: list[Annotated[int, Field(ge=1)]] = Field(min_length=1, max_length=UNKNOWN_GROUPING_MAX_FACES)
    action: Literal["assign", "dismiss"]
    employee_id: int | None = None
    add_to_gallery: bool = False

    @model_validator(mode="after")
    def _check_action(self) -> "UnknownFaceBulkAction":
        if self.action == "assign" and self.employee_id is None:
            raise ValueError("Choose the employee to assign these faces to")
        if self.action == "dismiss" and (self.employee_id is not None or self.add_to_gallery):
            raise ValueError("Dismiss takes no employee and no gallery option")
        return self


class UnknownFaceBulkSkipped(ApiModel):
    id: int
    reason: Literal["not_found", "already_reviewed"]


class UnknownFaceBulkResult(ApiModel):
    action: Literal["assign", "dismiss"]
    processed_ids: list[int]
    skipped: list[UnknownFaceBulkSkipped]
    attendance_updated: bool
    added_to_gallery: bool
    # How many of the assigned faces joined the employee's gallery as assigned photos (Q64).
    gallery_added: int = 0
    # The first face added to the gallery.
    gallery_face_id: int | None = None
    # Why no face was added (only set when none was).
    gallery_rejection_reason: str | None = None
