"""Domain exceptions and the global handlers that turn them into the error envelope (standards/04, 09)."""

import logging
from typing import Any

from facetrack_common.schemas.envelope import ErrorResponse
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


def _readable(message: str) -> str:
    """Pydantic prefixes validator messages with "Value error, "; users only need the sentence."""
    text = message.removeprefix("Value error, ")
    return text[:1].upper() + text[1:]


class DomainError(Exception):
    status_code = 400
    default_message = "Unable to process request."

    def __init__(self, message: str | None = None, errors: dict[str, Any] | None = None) -> None:
        self.message = message or self.default_message
        self.errors = errors or {}
        super().__init__(self.message)


class BadRequest(DomainError):
    status_code = 400


class Unauthorized(DomainError):
    status_code = 401
    default_message = "Authentication required."


class PermissionDenied(DomainError):
    status_code = 403
    default_message = "You do not have permission to perform this action."


class NotFound(DomainError):
    status_code = 404
    default_message = "Resource not found."


class Conflict(DomainError):
    status_code = 409
    default_message = "The request conflicts with the current state."


class ValidationFailed(DomainError):
    status_code = 422
    default_message = "Validation failed."


class RateLimited(DomainError):
    status_code = 429
    default_message = "Too many requests. Please try again later."


class EngineUnavailable(DomainError):
    status_code = 503
    default_message = "The recognition engine is unavailable. Please try again shortly."


def _envelope(status: int, message: str, errors: dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse(ErrorResponse(message=message, errors=errors or {}).model_dump(), status_code=status)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return _envelope(exc.status_code, exc.message, exc.errors)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors: dict[str, Any] = {}
        for error in exc.errors():
            location = [str(part) for part in error["loc"] if part not in ("body", "query", "path")]
            errors.setdefault(".".join(location) or "body", []).append(_readable(error["msg"]))
        return _envelope(422, "Validation failed.", errors)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _envelope(exc.status_code, str(exc.detail))

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error", extra={"error": type(exc).__name__})
        return _envelope(500, "An unexpected error occurred.")
