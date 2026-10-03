"""Response envelope helpers (standards/04, ADR-0002). Routers always use these."""

from collections.abc import Sequence

from facetrack_common.schemas.envelope import ApiResponse, PaginatedResponse, Pagination


def ok[T](data: T, message: str = "Request completed successfully.") -> ApiResponse[T]:
    return ApiResponse[T](message=message, data=data)


def created[T](data: T, message: str = "Created successfully.") -> ApiResponse[T]:
    return ApiResponse[T](message=message, data=data)


def paginated[T](
    items: Sequence[T], page: int, page_size: int, total: int, message: str
) -> PaginatedResponse[T]:
    return PaginatedResponse[T](
        message=message, data=list(items), pagination=Pagination(page=page, page_size=page_size, total=total)
    )
