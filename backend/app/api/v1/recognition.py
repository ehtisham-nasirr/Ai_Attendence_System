"""Recognition events (event log, void) and the unknown-face review queue (FR-17, FR-27, FR-28)."""

from datetime import datetime
from typing import Annotated

from facetrack_common.constants import RecognitionStatus, ReviewStatus
from facetrack_common.models import User
from facetrack_common.schemas.envelope import ApiResponse, PaginatedResponse
from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import DbDep, PageDep, ScopeDep, jpeg_response
from app.core.exceptions import NotFound
from app.core.responses import ok, paginated
from app.core.security import CurrentUser, Permission, has_permission, require_permission
from app.domain.recognition import service
from app.repositories import event_repo
from app.schemas.recognition import (
    EventOut,
    EventVoid,
    UnknownFaceAssign,
    UnknownFaceAssignResult,
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
