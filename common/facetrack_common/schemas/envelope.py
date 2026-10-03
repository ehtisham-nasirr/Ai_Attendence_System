"""The standard API response envelope (standards/04, ADR-0002), shared by backend and engine APIs."""

from typing import Any

from pydantic import BaseModel, Field


class ApiResponse[T](BaseModel):
    """Single-object response: `{success, message, data}`."""

    success: bool = True
    message: str
    data: T


class Pagination(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)


class PaginatedResponse[T](BaseModel):
    """List response: `{success, message, data: [...], pagination}`."""

    success: bool = True
    message: str
    data: list[T]
    pagination: Pagination


class ErrorResponse(BaseModel):
    """Error response: `{success: false, message, errors}`; `errors` is keyed by field name."""

    success: bool = False
    message: str
    errors: dict[str, Any] = Field(default_factory=dict)
