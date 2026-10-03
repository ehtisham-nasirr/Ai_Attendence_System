"""Polls each engine node for camera status (FR-3) and raises offline alerts (FR-4, FR-32)."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from celery import shared_task

from app.core.config import get_settings
from app.core.redis import get_sync_redis
from app.domain.cameras import status as camera_status
from app.domain.settings import service as settings_service
from app.services import engine_client, metrics_store
from app.worker import runtime

logger = logging.getLogger(__name__)
_ALERTED_KEY = "alerted:camera_offline:{camera_id}"
_ENGINE_ALERTED_KEY = "alerted:engine_down:{node}"


async def _node_load(url: str) -> int | None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(
            f"{url.rstrip('/')}/load",
            headers={"X-Engine-Token": get_settings().engine_api_token.get_secret_value()},
        )
    response.raise_for_status()
    return int(response.json()["data"]["level"])


def _bind[T](fn: Callable[[str], Awaitable[T]], url: str) -> Callable[[], Awaitable[T]]:
    def call() -> Awaitable[T]:
        return fn(url)

    return call


@shared_task(name="app.worker.tasks.cameras.sync_camera_status")
def sync_camera_status() -> dict[str, int]:
    from app.worker.tasks.notifications import send_alert  # noqa: PLC0415

    redis = get_sync_redis()
    summary = {"online_nodes": 0, "offline_nodes": 0}
    for node, url in get_settings().engine_nodes.items():
        try:
            statuses = runtime.run(_bind(engine_client.camera_statuses, url))
            level = runtime.run(_bind(_node_load, url))
            summary["online_nodes"] += 1
            redis.delete(_ENGINE_ALERTED_KEY.format(node=node))
        except (httpx.HTTPError, KeyError, ValueError):
            statuses, level = None, None
            summary["offline_nodes"] += 1
            if redis.set(_ENGINE_ALERTED_KEY.format(node=node), "1", nx=True, ex=6 * 3600):
                send_alert.delay(
                    f"Engine node '{node}' is not responding", "Recognition on its cameras has stopped."
                )

        async def apply(db: Any, n: str = node, s: Any = statuses, lv: Any = level) -> Any:
            return await camera_status.apply_node_status(db, n, s, lv)

        runtime.run_with_session(apply)

    async def overdue(db: Any) -> tuple[list[Any], int]:
        values = await settings_service.resolved(db)
        minutes = int(values["notifications.camera_offline_alert_min"])
        return await camera_status.offline_longer_than(db, minutes), minutes

    offline, minutes = runtime.run_with_session(overdue)
    metrics_store.set_value("cameras_offline", len(offline))
    for camera in offline:
        if redis.set(_ALERTED_KEY.format(camera_id=camera.id), "1", nx=True, ex=24 * 3600):
            send_alert.delay(
                f"Camera '{camera.name}' offline", f"No video for more than {minutes} minutes (FR-4)."
            )
    online_ids = {c.id for c in offline}
    for key in redis.scan_iter(match="alerted:camera_offline:*"):
        if int(str(key).rsplit(":", 1)[1]) not in online_ids:
            redis.delete(key)  # back online: alert again next time
    return summary
