"""Audit trail (FR-37): who, when, from where, old and new values. Never biometric data or secrets."""

from datetime import date, datetime, time
from enum import Enum
from typing import Any

from facetrack_common.models import AuditLog, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_context import get_request_context

# Fields never written to the audit log, whatever the entity.
_REDACTED = {
    "password",
    "password_hash",
    "rtsp_url",
    "substream_url",
    "rtsp_url_encrypted",
    "substream_url_encrypted",
    "embedding_encrypted",
    "key_hash",
    "token",
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bytes):
        return "[binary]"
    if isinstance(value, dict):
        return {k: ("[redacted]" if k in _REDACTED else _jsonable(v)) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(v) for v in value]
    return value


async def record(
    db: AsyncSession,
    actor: User | None,
    action: str,
    entity: str,
    entity_id: object | None = None,
    old: dict[str, Any] | None = None,
    new: dict[str, Any] | None = None,
) -> None:
    """Adds an audit entry to the current transaction (committed together with the change)."""
    context = get_request_context()
    db.add(
        AuditLog(
            user_id=actor.id if actor else None,
            action=action,
            entity=entity,
            entity_id=None if entity_id is None else str(entity_id),
            old_values=_jsonable(old) if old else None,
            new_values=_jsonable(new) if new else None,
            ip=context.ip,
            user_agent=context.user_agent,
        )
    )
