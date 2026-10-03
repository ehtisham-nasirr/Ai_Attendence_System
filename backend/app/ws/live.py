"""`/ws/live` — live feed for the dashboard and live view (standards/02, 04).

Authenticates with the same session cookie and applies the same role scoping as the REST API.
It only forwards messages published on Redis Pub/Sub; it never queries business data itself.
"""

import asyncio
import json
import logging
from typing import Any

from facetrack_common.constants import LIVE_UPDATES_CHANNEL, WsMessageType
from facetrack_common.models import User
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.exceptions import Unauthorized
from app.core.metrics import WS_CONNECTIONS
from app.core.redis import get_async_redis
from app.core.security import (
    ACCESS_COOKIE,
    DataScope,
    Permission,
    data_scope,
    decode_token,
    has_permission,
    is_revoked,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_CLOSE_UNAUTHORISED = 4401


async def _authenticate(websocket: WebSocket) -> tuple[User, DataScope] | None:
    token = websocket.cookies.get(ACCESS_COOKIE)
    if not token:
        return None
    try:
        claims = decode_token(token, get_settings(), "access")
    except Unauthorized:
        return None
    if await is_revoked(claims):
        return None
    async with get_sessionmaker()() as db:
        user = await db.scalar(select(User).where(User.id == int(claims["sub"]), User.deleted_at.is_(None)))
        if user is None or not user.is_active or user.session_version != claims.get("sv"):
            return None
        return user, await data_scope(db, user)


def allowed(message: dict[str, Any], user: User, scope: DataScope) -> bool:
    """Same visibility rules as the REST endpoints behind each message type."""
    kind = message.get("type")
    data = message.get("data") or {}
    if kind in (WsMessageType.CAMERA_STATUS_CHANGED, WsMessageType.LOAD_LEVEL_CHANGED):
        return has_permission(user, Permission.DASHBOARD_VIEW) or has_permission(user, Permission.LIVE_VIEW)
    if kind == WsMessageType.RECOGNITION_CREATED:
        if has_permission(user, Permission.EVENTS_VIEW):
            return True
        employee_id = data.get("employee_id")
        return (
            has_permission(user, Permission.DASHBOARD_VIEW)
            and employee_id is not None
            and scope.allows(data.get("department_id"), int(employee_id))
        )
    if kind == WsMessageType.ATTENDANCE_UPDATED:
        employee_id = data.get("employee_id")
        return (
            has_permission(user, Permission.ATTENDANCE_VIEW)
            and employee_id is not None
            and scope.allows(data.get("department_id"), int(employee_id))
        )
    return False


@router.websocket("/ws/live")
async def live_feed(websocket: WebSocket) -> None:
    identity = await _authenticate(websocket)
    if identity is None:
        await websocket.close(code=_CLOSE_UNAUTHORISED)
        return
    user, scope = identity
    await websocket.accept()
    WS_CONNECTIONS.inc()
    pubsub = get_async_redis().pubsub(ignore_subscribe_messages=True)
    await pubsub.subscribe(LIVE_UPDATES_CHANNEL)

    async def forward() -> None:
        async for raw in pubsub.listen():
            try:
                message = json.loads(raw["data"])
            except (TypeError, ValueError):
                continue
            if allowed(message, user, scope):
                await websocket.send_text(json.dumps(message))

    async def drain_client() -> None:
        while True:
            await websocket.receive_text()  # pings from the client; content ignored

    tasks = [asyncio.create_task(forward()), asyncio.create_task(drain_client())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            task.cancel()
        await pubsub.unsubscribe(LIVE_UPDATES_CHANNEL)
        await pubsub.aclose()  # type: ignore[no-untyped-call]  # redis-py stub gap
