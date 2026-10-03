"""FastAPI app factory: routers, middleware, exception handlers, metrics (requirements §12)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from facetrack_common.jsonlog import configure_logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.routing import APIRoute
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

from app.api import internal
from app.api.v1 import (
    attendance,
    auth,
    cameras,
    employees,
    integration,
    organization,
    recognition,
    reports,
    system,
    users,
)
from app.core.config import Settings, get_settings
from app.core.db import get_engine
from app.core.exceptions import register_exception_handlers
from app.core.middleware import RequestContextMiddleware
from app.services.metrics_store import RedisMetricsCollector
from app.ws import live

API_PREFIX = "/api/v1"
_collector_registered = False


def _register_collector() -> None:
    global _collector_registered  # noqa: PLW0603  # register once per process
    if not _collector_registered:
        REGISTRY.register(RedisMetricsCollector())
        _collector_registered = True


def _operation_id(route: APIRoute) -> str:
    """Route function name as the OpenAPI operationId, so the generated portal client reads naturally."""
    return route.name


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.service_name, settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await get_engine().dispose()

    docs = settings.api_docs_enabled and not settings.is_production  # standards/06
    app = FastAPI(
        title="FaceTrack API",
        version="1.0.0",
        description=(
            "FaceTrack attendance system API (requirements §12). "
            "Portal: session cookie + CSRF header; integrations: X-API-Key."
        ),
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
    )
    register_exception_handlers(app)
    app.add_middleware(RequestContextMiddleware, settings=settings)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,  # exact portal origin(s), never "*"
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
        )
    for router in (
        auth.router,
        users.router,
        organization.router,
        employees.router,
        cameras.router,
        recognition.router,
        attendance.router,
        reports.router,
        integration.router,
        system.router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    app.include_router(live.router)
    app.include_router(internal.router)

    _register_collector()

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
