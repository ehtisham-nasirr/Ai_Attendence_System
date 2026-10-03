"""Internal engine API (requirements §12.2). Reachable only from the backend network."""

import base64
from typing import Annotated

import cv2
import numpy as np
from facetrack_common.constants import CRYPTO_PURPOSE_EMBEDDING
from facetrack_common.schemas.engine import (
    CameraRuntimeStatus,
    CameraSyncResult,
    CameraTestRequest,
    CameraTestResult,
    EmbedResult,
    EngineHealth,
    GalleryReloadResult,
    LoadStatus,
)
from facetrack_common.schemas.envelope import ApiResponse
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.deps import SupervisorDep, require_token
from app.scheduler.supervisor import EngineUnavailableError

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # standards/14: photo <= 5 MB
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

protected = APIRouter(dependencies=[Depends(require_token)])
public = APIRouter()


@protected.post(
    "/embed", response_model=ApiResponse[EmbedResult], summary="Validate a photo and embed its face"
)
async def embed(supervisor: SupervisorDep, image: Annotated[UploadFile, File()]) -> ApiResponse[EmbedResult]:
    """FR-9: exactly one face, width >= minimum, quality and sharpness gates. The embedding is returned
    AES-256-GCM encrypted (base64) and only when the photo is accepted."""
    data = await image.read(MAX_IMAGE_BYTES + 1)
    model = supervisor.settings.embedder
    if len(data) > MAX_IMAGE_BYTES or not (data.startswith(_JPEG_MAGIC) or data.startswith(_PNG_MAGIC)):
        return ApiResponse(
            message="Image rejected.",
            data=EmbedResult(
                accepted=False, rejection_reason="invalid_image", face_count=0, model_name=model
            ),
        )
    decoded = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        return ApiResponse(
            message="Image rejected.",
            data=EmbedResult(
                accepted=False, rejection_reason="invalid_image", face_count=0, model_name=model
            ),
        )
    try:
        outcome = await supervisor.embed_image(decoded)
    except EngineUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Recognition engine is busy.") from exc
    encrypted = None
    if outcome.embedding is not None:
        token = supervisor.cipher.encrypt_embedding(outcome.embedding, CRYPTO_PURPOSE_EMBEDDING)
        encrypted = base64.b64encode(token).decode("ascii")
    result = EmbedResult(
        accepted=outcome.accepted,
        rejection_reason=outcome.rejection_reason,
        face_count=outcome.face_count,
        face_width_px=outcome.face_width_px,
        detector_score=outcome.detector_score,
        quality_score=outcome.quality_score,
        blur_variance=outcome.blur_variance,
        model_name=model,
        embedding_dim=len(outcome.embedding) if outcome.embedding is not None else None,
        embedding_encrypted=encrypted,
    )
    return ApiResponse(message="Photo accepted." if result.accepted else "Photo rejected.", data=result)


@protected.post(
    "/gallery/reload", response_model=ApiResponse[GalleryReloadResult], summary="Reload FAISS gallery"
)
async def reload_gallery(supervisor: SupervisorDep) -> ApiResponse[GalleryReloadResult]:
    return ApiResponse(message="Gallery reloaded.", data=await supervisor.reload_gallery())


@protected.post(
    "/cameras/sync", response_model=ApiResponse[CameraSyncResult], summary="Start/stop/reconfigure"
)
async def sync_cameras(supervisor: SupervisorDep) -> ApiResponse[CameraSyncResult]:
    return ApiResponse(message="Cameras synchronised.", data=await supervisor.sync_cameras())


@protected.get(
    "/cameras/status",
    response_model=ApiResponse[list[CameraRuntimeStatus]],
    summary="Per-camera runtime status",
)
async def cameras_status(supervisor: SupervisorDep) -> ApiResponse[list[CameraRuntimeStatus]]:
    return ApiResponse(message="Camera status retrieved.", data=supervisor.camera_statuses())


@protected.post("/cameras/test", response_model=ApiResponse[CameraTestResult], summary="FR-2 connection test")
async def test_camera(supervisor: SupervisorDep, payload: CameraTestRequest) -> ApiResponse[CameraTestResult]:
    result = await supervisor.test_camera(payload.camera_id, payload.use_substream)
    return ApiResponse(message="Camera reachable." if result.ok else "Camera not reachable.", data=result)


@protected.get("/load", response_model=ApiResponse[LoadStatus], summary="CPU and degradation step")
async def load(supervisor: SupervisorDep) -> ApiResponse[LoadStatus]:
    return ApiResponse(message="Load retrieved.", data=supervisor.load_status())


@public.get("/health", response_model=ApiResponse[EngineHealth], summary="Liveness and readiness")
async def health(supervisor: SupervisorDep) -> ApiResponse[EngineHealth]:
    return ApiResponse(message="Engine health.", data=await supervisor.health())


@public.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
