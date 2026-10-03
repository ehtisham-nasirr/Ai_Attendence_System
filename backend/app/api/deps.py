"""Shared router dependencies."""

from typing import Annotated

from fastapi import Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.pagination import PageParams, page_params
from app.core.security import CurrentUser, DataScope, data_scope

DbDep = Annotated[AsyncSession, Depends(get_db)]
PageDep = Annotated[PageParams, Depends(page_params)]


async def get_scope(db: DbDep, user: CurrentUser) -> DataScope:
    return await data_scope(db, user)


ScopeDep = Annotated[DataScope, Depends(get_scope)]


def jpeg_response(data: bytes) -> Response:
    # Biometric images: never cached by browsers or proxies (standards/18).
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store, private"})
