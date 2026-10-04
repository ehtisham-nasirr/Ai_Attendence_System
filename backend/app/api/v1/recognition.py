"""Recognition events (event log, void) and the unknown-face review queue (FR-17, FR-27, FR-28)."""

from datetime import datetime
from typing import Annotated

from facetrack_common.constants import RecognitionStatus, ReviewStatus
from facetrack_common.models import User
from facetrack_common.schemas.envelope import ApiResponse, PaginatedResponse
from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import DbDep, PageDep, ScopeDep, jpeg_response
from app.core.exceptions import NotFound, PermissionDenied
from app.core.responses import ok, paginated
from app.core.security import CurrentUser, Permission, has_permission, require_permission
from app.domain.recognition import service
from app.repositories import event_repo
from app.schemas.recognition import (
    EventOut,
    EventVoid,
    UnknownFaceAssign,
    UnknownFaceAssignResult,
    UnknownFaceBulkAction,
    UnknownFaceBulkResult,
    UnknownFaceBulkSkipped,
    UnknownFaceGroupsResponse,
    UnknownFaceOut,
    UnknownFaceUpdate,
)

router = APIRouter(tags=["recognition"])
EventViewer = Annotated[User, require_permission(Permission.EVENTS_VIEW)]
EventVoider = Annotated[User, require_permission(Permission.EVENTS_VOID)]
Reviewer = Annotated[User, require_permission(Permission.UNKNOWN_FACES_REVIEW)]
Assigner = Annotated[User, require_permission(Permission.UNKNOWN_FACES_ASSIGN)]


@router.get("/events", response_model=PaginatedResponse[EventOut], summary="Recognition events")
async def list_events(
    db: DbDep,
    page: PageDep,
    _: EventViewer,
    camera_id: int | None = None,
    employee_id: int | None = None,
    status: RecognitionStatus | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> PaginatedResponse[EventOut]:
    items, total = await event_repo.list_events(
        db,
        page,
        camera_id=camera_id,
        employee_id=employee_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    return paginated(
        [service.event_to_out(e) for e in items], page.page, page.page_size, total, "Events retrieved."
    )


@router.post(
    "/events/{event_id}/void", response_model=ApiResponse[EventOut], summary="Mark a false recognition"
)
async def void_event(
    event_id: int, payload: EventVoid, db: DbDep, actor: EventVoider
) -> ApiResponse[EventOut]:
    """FR-28: the event is voided (kept for threshold tuning) and the attendance day is rebuilt without it."""
    event = await service.void_event(db, event_id, payload.reason, actor)
    return ok(service.event_to_out(event), "Event voided.")


@router.get("/events/{event_id}/snapshot", response_class=Response, summary="Event face snapshot")
async def event_snapshot(event_id: int, db: DbDep, user: CurrentUser, scope: ScopeDep) -> Response:
    """Allowed for event viewers, and for attendance viewers within their scope (check-in hover)."""
    event = await event_repo.get_event(db, event_id)
    if event is None:
        raise NotFound("Event not found.")
    allowed = has_permission(user, Permission.EVENTS_VIEW) or (
        has_permission(user, Permission.ATTENDANCE_VIEW)
        and event.employee is not None
        and scope.allows(event.employee.department_id, event.employee.id)
    )
    if not allowed:
        raise NotFound("Event not found.")
    return jpeg_response(await service.event_snapshot(event))


@router.get(
    "/unknown-faces", response_model=PaginatedResponse[UnknownFaceOut], summary="Unknown-face review queue"
)
async def list_unknown_faces(
    db: DbDep,
    page: PageDep,
    actor: Reviewer,
    review_status: ReviewStatus | None = ReviewStatus.PENDING,
    camera_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> PaginatedResponse[UnknownFaceOut]:
    faces, total = await service.review_queue(
        db,
        page,
        actor,
        review_status=review_status,
        camera_id=camera_id,
        date_from=date_from,
        date_to=date_to,
    )
    return paginated(faces, page.page, page.page_size, total, "Unknown faces retrieved.")


@router.get(
    "/unknown-faces/groups",
    response_model=UnknownFaceGroupsResponse,
    summary="Unknown-face review queue, one card per person",
)
async def list_unknown_face_groups(
    db: DbDep,
    page: PageDep,
    actor: Reviewer,
    review_status: ReviewStatus | None = ReviewStatus.PENDING,
    camera_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> UnknownFaceGroupsResponse:
    """§13 screen 9: faces that look like the same person are grouped over the whole queue, so one
    person is one card on one page. Pagination counts groups. `sort`: `last_seen_at` (default
    `-last_seen_at`), `first_seen_at` or `face_count`. `grouping.truncated` is true when only the newest
    `grouping.max_faces` faces were grouped. Viewing is audit-logged."""
    groups, total, coverage = await service.review_groups(
        db,
        page,
        actor,
        review_status=review_status,
        camera_id=camera_id,
        date_from=date_from,
        date_to=date_to,
    )
    base = paginated(groups, page.page, page.page_size, total, "Unknown-face groups retrieved.")
    return UnknownFaceGroupsResponse(
        message=base.message, data=base.data, pagination=base.pagination, grouping=coverage
    )


@router.post(
    "/unknown-faces/bulk",
    response_model=ApiResponse[UnknownFaceBulkResult],
    summary="Assign or dismiss many unknown faces at once",
)
async def bulk_review_unknown_faces(
    payload: UnknownFaceBulkAction, db: DbDep, actor: Reviewer
) -> ApiResponse[UnknownFaceBulkResult]:
    """FR-27 for a whole group card. `assign` needs the same permission as the single assign (Admin,
    HR); `dismiss` is open to every reviewer. Faces that are gone or already reviewed are skipped and
    listed in `skipped`; the rest are decided in one transaction. With `add_to_gallery`, only the first
    assigned face with a snapshot is offered to the gallery, after the FR-9 checks (requires consent)."""
    if payload.action == "assign" and not has_permission(actor, Permission.UNKNOWN_FACES_ASSIGN):
        raise PermissionDenied()
    outcome = await service.bulk_review(
        db, payload.face_ids, payload.action, payload.employee_id, payload.add_to_gallery, actor
    )
    result = UnknownFaceBulkResult(
        action=payload.action,
        processed_ids=outcome.processed_ids,
        skipped=[UnknownFaceBulkSkipped(id=face_id, reason=reason) for face_id, reason in outcome.skipped],
        attendance_updated=outcome.attendance_updated,
        added_to_gallery=outcome.added_to_gallery,
        gallery_face_id=outcome.gallery_face_id,
        gallery_rejection_reason=outcome.gallery_rejection_reason,
    )
    verb = "assigned" if payload.action == "assign" else "dismissed"
    message = f"{len(outcome.processed_ids)} unknown face(s) {verb}."
    if outcome.skipped:
        message += f" {len(outcome.skipped)} skipped (already reviewed or not found)."
    return ok(result, message)


@router.get("/unknown-faces/{unknown_id}/snapshot", response_class=Response, summary="Unknown face snapshot")
async def unknown_snapshot(unknown_id: int, db: DbDep, _: Reviewer) -> Response:
    face = await event_repo.get_unknown(db, unknown_id)
    if face is None:
        raise NotFound("Unknown face not found.")
    return jpeg_response(await service.event_snapshot(face))


@router.post(
    "/unknown-faces/{unknown_id}/assign",
    response_model=ApiResponse[UnknownFaceAssignResult],
    summary="Assign an unknown face to an employee",
)
async def assign_unknown(
    unknown_id: int, payload: UnknownFaceAssign, db: DbDep, actor: Assigner
) -> ApiResponse[UnknownFaceAssignResult]:
    """FR-27: creates the attendance sighting; with `add_to_gallery` the snapshot is also enrolled after
    the FR-9 checks (requires consent)."""
    face, updated, added, rejection = await service.assign_unknown(
        db, unknown_id, payload.employee_id, payload.add_to_gallery, actor
    )
    result = UnknownFaceAssignResult(
        unknown_face=service.unknown_to_out(face),
        attendance_updated=updated,
        added_to_gallery=added,
        gallery_rejection_reason=rejection,
    )
    return ok(result, "Unknown face assigned.")


@router.patch("/unknown-faces/{unknown_id}", response_model=ApiResponse[UnknownFaceOut], summary="Dismiss")
async def update_unknown(
    unknown_id: int, payload: UnknownFaceUpdate, db: DbDep, actor: Reviewer
) -> ApiResponse[UnknownFaceOut]:
    face = await service.dismiss_unknown(db, unknown_id, actor)
    return ok(service.unknown_to_out(face), "Unknown face dismissed.")
