"""MediaMTX control API: one on-demand path per camera for live view (requirements §7, §13 screen 3).

The camera is only pulled while someone watches (`sourceOnDemand`), so live view adds no load
otherwise. Browsers never see camera credentials: they get a WebRTC URL plus a short-lived token.
"""

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def path_name(camera_id: int) -> str:
    return f"cam-{camera_id}"


async def upsert_path(camera_id: int, source_url: str) -> bool:
    base = get_settings().mediamtx_api_url.rstrip("/")
    name = path_name(camera_id)
    config = {"source": source_url, "sourceOnDemand": True, "sourceProtocol": "tcp"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(f"{base}/v3/config/paths/replace/{name}", json=config)
            if response.status_code == 404:
                response = await client.post(f"{base}/v3/config/paths/add/{name}", json=config)
        return response.status_code in (200, 201)
    except httpx.HTTPError:
        logger.warning(
            "MediaMTX not reachable; live view path not configured", extra={"camera_id": camera_id}
        )
        return False


async def delete_path(camera_id: int) -> None:
    base = get_settings().mediamtx_api_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.delete(f"{base}/v3/config/paths/delete/{path_name(camera_id)}")
    except httpx.HTTPError:
        logger.warning("MediaMTX not reachable; live view path not removed", extra={"camera_id": camera_id})
