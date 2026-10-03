"""Engine app factory: internal FastAPI API + the supervisor that runs cameras and the inference pool."""

import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from facetrack_common.jsonlog import configure_logging
from facetrack_common.schemas.envelope import ErrorResponse
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import protected, public
from app.config import EngineSettings, get_settings
from app.scheduler.supervisor import EngineSupervisor


def _pin_library_threads(settings: EngineSettings) -> None:
    """Set before workers spawn so no numeric library grabs every core (standards/17 §4)."""
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = str(settings.threads_per_worker)


def create_app(
    settings: EngineSettings | None = None,
    supervisor_factory: Callable[[EngineSettings], EngineSupervisor] = EngineSupervisor,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging("engine", settings.log_level)
    _pin_library_threads(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        supervisor = supervisor_factory(settings)
        app.state.supervisor = supervisor
        await supervisor.start()
        try:
            yield
        finally:
            await supervisor.stop()

    is_production = settings.environment == "production"
    app = FastAPI(
        title="FaceTrack engine (internal)",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if is_production else "/docs",
        openapi_url=None if is_production else "/openapi.json",
    )
    app.state.settings = settings

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(ErrorResponse(message=str(exc.detail)).model_dump(), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = {".".join(str(p) for p in e["loc"][1:]) or "body": e["msg"] for e in exc.errors()}
        body = ErrorResponse(message="Validation failed.", errors=errors)
        return JSONResponse(body.model_dump(), status_code=422)

    app.include_router(public)
    app.include_router(protected)
    return app
