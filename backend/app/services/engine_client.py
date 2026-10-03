"""Client for the internal engine API (§12.2) and engine control notifications (FR-19)."""

import json
import logging
from typing import Any

import httpx
from facetrack_common.constants import ENGINE_CONTROL_CHANNEL
from facetrack_common.schemas.engine import CameraRuntimeStatus, CameraTestResult, EmbedResult

from app.core.config import get_settings
from app.core.exceptions import EngineUnavailable
from app.core.redis import get_async_redis

logger = logging.getLogger(__name__)


def _headers() -> dict[str, str]:
    return {"X-Engine-Token": get_settings().engine_api_token.get_secret_value()}


def _node_url(node: str | None) -> str:
    nodes = get_settings().engine_nodes
    if node and node in nodes:
        return nodes[node].rstrip("/")
    return next(iter(nodes.values())).rstrip("/")


async def _post(url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=get_settings().engine_timeout_s) as client:
            response = await client.post(url, headers=_headers(), **kwargs)
    except httpx.HTTPError as exc:
        logger.warning("engine unreachable", extra={"error": type(exc).__name__})
        raise EngineUnavailable() from exc
    if response.status_code != 200:
        raise EngineUnavailable()
    body: dict[str, Any] = response.json()
    return body


async def embed_photo(image: bytes, node: str | None = None) -> EmbedResult:
    """FR-9 validation + embedding of one enrollment photo."""
    body = await _post(
        f"{_node_url(node)}/embed", files={"image": ("photo.jpg", image, "application/octet-stream")}
    )
    return EmbedResult.model_validate(body["data"])


async def test_camera(camera_id: int, node: str | None, use_substream: bool = False) -> CameraTestResult:
    body = await _post(
        f"{_node_url(node)}/cameras/test", json={"camera_id": camera_id, "use_substream": use_substream}
    )
    return CameraTestResult.model_validate(body["data"])


async def camera_statuses(node_url: str) -> list[CameraRuntimeStatus]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{node_url.rstrip('/')}/cameras/status", headers=_headers())
    response.raise_for_status()
    return [CameraRuntimeStatus.model_validate(item) for item in response.json()["data"]]


async def notify_engines(command: str) -> None:
    """Broadcasts `gallery_reload` / `cameras_sync` to every engine node via Redis (standards/17 §9)."""
    if command not in {"gallery_reload", "cameras_sync"}:
        raise ValueError(command)
    try:
        await get_async_redis().publish(ENGINE_CONTROL_CHANNEL, json.dumps({"type": command}))
    except Exception:  # Redis down: engines reload on restart; log loudly instead of failing the request
        logger.error("engine notification not published", extra={"command": command})
