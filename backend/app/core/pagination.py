"""Pagination and sorting parameters (standards/04: page, page_size default 20 max 200, sort=-field)."""

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailed


@dataclass(frozen=True)
class PageParams:
    page: int
    page_size: int
    sort: str | None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
    sort: Annotated[str | None, Query(max_length=64, pattern=r"^-?[a-z_]+$")] = None,
) -> PageParams:
    return PageParams(page, page_size, sort)


def apply_sort[T: Any](stmt: Select[T], sort: str | None, allowed: dict[str, Any], default: Any) -> Select[T]:
    """Applies `sort=field` / `sort=-field` using only whitelisted columns."""
    if not sort:
        return stmt.order_by(default)
    descending = sort.startswith("-")
    column = allowed.get(sort.lstrip("-"))
    if column is None:
        raise ValidationFailed(errors={"sort": [f"Sorting by '{sort.lstrip('-')}' is not supported."]})
    return stmt.order_by(column.desc() if descending else column.asc(), default)


async def fetch_page[T: Any](db: AsyncSession, stmt: Select[T], params: PageParams) -> tuple[list[Any], int]:
    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = (await db.execute(stmt.offset(params.offset).limit(params.page_size))).unique()
    return list(rows.scalars().all()), int(total)
