"""Publishes `/ws/live` messages on Redis Pub/Sub (standards/02, 04). Fire-and-forget."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from facetrack_common.constants import LIVE_UPDATES_CHANNEL, WsMessageType

from app.core.redis import get_async_redis, get_sync_redis

logger = logging.getLogger(__name__)


def build_message(message_type: WsMessageType, data: dict[str, Any]) -> str:
    sent_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return json.dumps({"type": message_type.value, "data": data, "sent_at": sent_at}, default=str)


async def publish(message_type: WsMessageType, data: dict[str, Any]) -> None:
    try:
        await get_async_redis().publish(LIVE_UPDATES_CHANNEL, build_message(message_type, data))
    except Exception:  # live updates are best-effort; the REST API stays authoritative
        logger.warning("live update not published", extra={"type": message_type.value})


def publish_sync(message_type: WsMessageType, data: dict[str, Any]) -> None:
    try:
        get_sync_redis().publish(LIVE_UPDATES_CHANNEL, build_message(message_type, data))
    except Exception:
        logger.warning("live update not published", extra={"type": message_type.value})
