"""Per-request context (request id, client IP, user agent) for logging and the audit trail (FR-37)."""

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    request_id: str = "-"
    ip: str | None = None
    user_agent: str | None = None


_current: ContextVar[RequestContext] = ContextVar("request_context", default=RequestContext())  # noqa: B039


def set_request_context(context: RequestContext) -> None:
    _current.set(context)


def get_request_context() -> RequestContext:
    return _current.get()
