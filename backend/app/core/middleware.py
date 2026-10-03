"""HTTP middleware: request id + context, security headers, structured access metrics."""

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import Settings
from app.core.metrics import HTTP_LATENCY, HTTP_REQUESTS
from app.core.request_context import RequestContext, set_request_context

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cache-Control": "no-store",
}


def _client_ip(request: Request) -> str | None:
    # Nginx sets X-Real-IP; the backend is never exposed directly.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else None)


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        set_request_context(
            RequestContext(request_id, _client_ip(request), (request.headers.get("user-agent") or "")[:500])
        )
        started = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        HTTP_REQUESTS.labels(request.method, route_path, str(response.status_code)).inc()
        HTTP_LATENCY.labels(request.method, route_path).observe(time.perf_counter() - started)
        response.headers["X-Request-ID"] = request_id
        if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/docs"):
            for header, value in _SECURITY_HEADERS.items():
                response.headers.setdefault(header, value)
        if self._settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
