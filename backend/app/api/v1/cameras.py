"""Cameras (FR-1..FR-6, §13 screens 3 and 6)."""

from typing import Annotated

from facetrack_common.constants import CameraRole
from facetrack_common.models import Camera, User
from facetrack_common.schemas.envelope import ApiResponse, PaginatedResponse
from fastapi import APIRouter, Response, status

from app.api.deps import DbDep, PageDep
from app.core.exceptions import NotFound
from app.core.responses import created, ok, paginated
from app.core.security import Permission, require_permission
from app.domain.cameras import service
from app.repositories import camera_repo
from app.repositories.base import get_live
from app.schemas.camera import (
    CameraCreate,
    CameraLiveOut,
    CameraOut,
    CameraStreamUrlsOut,
    CameraTestOut,
    CameraUpdate,
)

router = APIRouter(prefix="/cameras", tags=["cameras"])
Operator = Annotated[User, require_permission(Permission.CAMERAS_MANAGE)]
Viewer = Annotated[User, require_permission(Permission.LIVE_VIEW)]


@router.get("", response_model=PaginatedResponse[CameraOut], summary="List cameras with live health")
async def list_cameras(
    db: DbDep,
    page: PageDep,
    _: Viewer,
    location_id: int | None = None,
    role: CameraRole | None = None,
    engine_node: str | None = None,
) -> PaginatedResponse[CameraOut]:
    items, total = await camera_repo.list_cameras(db, page, location_id, role, engine_node)
    return paginated(await service.to_out(items), page.page, page.page_size, total, "Cameras retrieved.")


@router.get("/{camera_id}", response_model=ApiResponse[CameraOut])
async def get_camera(camera_id: int, db: DbDep, _: Viewer) -> ApiResponse[CameraOut]:
    camera = await get_live(db, Camera, camera_id)
    if camera is None:
        raise NotFound("Camera not found.")
    return ok((await service.to_out([camera]))[0], "Camera retrieved.")


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[CameraOut], summary="Add a camera"
)
async def create_camera(payload: CameraCreate, db: DbDep, actor: Operator) -> ApiResponse[CameraOut]:
    """The RTSP URL (with credentials) is stored AES-256 encrypted (FR-1, NFR-8). It is returned only by
    `GET /cameras/{id}/stream-urls`, to camera managers (Q63)."""
    camera = await service.create_camera(db, payload, actor)
    return created((await service.to_out([camera]))[0], "Camera created.")


@router.put("/{camera_id}", response_model=ApiResponse[CameraOut])
async def update_camera(
    camera_id: int, payload: CameraUpdate, db: DbDep, actor: Operator
) -> ApiResponse[CameraOut]:
    camera = await service.update_camera(db, camera_id, payload, actor)
    return ok((await service.to_out([camera]))[0], "Camera updated.")


@router.get(
    "/{camera_id}/stream-urls",
    response_model=ApiResponse[CameraStreamUrlsOut],
    summary="Saved stream links for the edit form (camera managers)",
)
async def stream_urls(
    camera_id: int, db: DbDep, actor: Operator, response: Response
) -> ApiResponse[CameraStreamUrlsOut]:
    response.headers["Cache-Control"] = "no-store"
    return ok(await service.stream_urls(db, camera_id, actor), "Stream links retrieved.")


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(camera_id: int, db: DbDep, actor: Operator) -> None:
    await service.delete_camera(db, camera_id, actor)


@router.post(
    "/{camera_id}/test", response_model=ApiResponse[CameraTestOut], summary="Test RTSP and return a snapshot"
)
async def test_camera(
    camera_id: int, db: DbDep, actor: Operator, use_substream: bool = False
) -> ApiResponse[CameraTestOut]:
    """FR-2. Returns 503 when the engine is unreachable."""
    result = await service.test_camera(db, camera_id, use_substream, actor)
    return ok(result, "Camera reachable." if result.ok else "Camera not reachable.")


@router.get("/{camera_id}/live", response_model=ApiResponse[CameraLiveOut], summary="WebRTC live view URL")
async def live_view(camera_id: int, db: DbDep, actor: Viewer) -> ApiResponse[CameraLiveOut]:
    return ok(await service.live_view(db, camera_id, actor), "Live view ready.")
