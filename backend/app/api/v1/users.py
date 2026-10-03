"""Portal users and roles (Super Admin)."""

from typing import Annotated

from facetrack_common.models import User
from facetrack_common.schemas.envelope import ApiResponse, PaginatedResponse
from fastapi import APIRouter, Query, status

from app.api.deps import DbDep, PageDep
from app.core.exceptions import NotFound
from app.core.responses import created, ok, paginated
from app.core.security import Permission, require_permission
from app.domain.users import service
from app.repositories import user_repo
from app.repositories.base import get_live
from app.schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter(
    prefix="/users", tags=["users"], dependencies=[require_permission(Permission.USERS_MANAGE)]
)
Admin = Annotated[User, require_permission(Permission.USERS_MANAGE)]


@router.get("", response_model=PaginatedResponse[UserOut], summary="List users")
async def list_users(
    db: DbDep,
    page: PageDep,
    search: Annotated[str | None, Query(max_length=100)] = None,
    role: str | None = None,
) -> PaginatedResponse[UserOut]:
    users, total = await user_repo.list_users(db, page, search, role)
    return paginated([service.to_out(u) for u in users], page.page, page.page_size, total, "Users retrieved.")


@router.get("/{user_id}", response_model=ApiResponse[UserOut], summary="Get a user")
async def get_user(user_id: int, db: DbDep) -> ApiResponse[UserOut]:
    user = await get_live(db, User, user_id)
    if user is None:
        raise NotFound("User not found.")
    return ok(service.to_out(user), "User retrieved.")


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[UserOut], summary="Create a user"
)
async def create_user(payload: UserCreate, db: DbDep, actor: Admin) -> ApiResponse[UserOut]:
    return created(service.to_out(await service.create_user(db, payload, actor)), "User created.")


@router.put("/{user_id}", response_model=ApiResponse[UserOut], summary="Update a user")
async def update_user(user_id: int, payload: UserUpdate, db: DbDep, actor: Admin) -> ApiResponse[UserOut]:
    return ok(service.to_out(await service.update_user(db, user_id, payload, actor)), "User updated.")


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a user")
async def delete_user(user_id: int, db: DbDep, actor: Admin) -> None:
    await service.delete_user(db, user_id, actor)
