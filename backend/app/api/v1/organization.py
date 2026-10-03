"""Locations, departments, shifts, holidays (Settings tabs; FR-21, FR-36). Read: staff; write: Admin."""

from datetime import date
from typing import Annotated

from facetrack_common.models import Department, Shift, User
from facetrack_common.schemas.envelope import ApiResponse, PaginatedResponse
from fastapi import APIRouter, status

from app.api.deps import DbDep, PageDep
from app.core.exceptions import NotFound
from app.core.responses import created, ok, paginated
from app.core.security import Permission, require_permission
from app.domain.organization import service
from app.repositories import organization_repo as repo
from app.repositories.base import get_live
from app.schemas.organization import (
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
    HolidayCreate,
    HolidayOut,
    HolidayUpdate,
    LocationCreate,
    LocationOut,
    LocationUpdate,
    ShiftCreate,
    ShiftOut,
    ShiftUpdate,
)

router = APIRouter(tags=["organization"])
Viewer = Annotated[User, require_permission(Permission.ORGANIZATION_VIEW)]
Admin = Annotated[User, require_permission(Permission.SETTINGS_MANAGE)]


# --- locations ---
@router.get("/locations", response_model=PaginatedResponse[LocationOut], summary="List locations")
async def list_locations(db: DbDep, page: PageDep, _: Viewer) -> PaginatedResponse[LocationOut]:
    items, total = await repo.list_locations(db, page)
    return paginated(
        [LocationOut.model_validate(i) for i in items],
        page.page,
        page.page_size,
        total,
        "Locations retrieved.",
    )


@router.post("/locations", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[LocationOut])
async def create_location(payload: LocationCreate, db: DbDep, actor: Admin) -> ApiResponse[LocationOut]:
    return created(
        LocationOut.model_validate(await service.create_location(db, payload, actor)), "Location created."
    )


@router.put("/locations/{location_id}", response_model=ApiResponse[LocationOut])
async def update_location(
    location_id: int, payload: LocationUpdate, db: DbDep, actor: Admin
) -> ApiResponse[LocationOut]:
    location = await service.update_location(db, location_id, payload, actor)
    return ok(LocationOut.model_validate(location), "Location updated.")


@router.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_location(location_id: int, db: DbDep, actor: Admin) -> None:
    await service.delete_location(db, location_id, actor)


# --- departments ---
@router.get("/departments", response_model=PaginatedResponse[DepartmentOut], summary="List departments")
async def list_departments(db: DbDep, page: PageDep, _: Viewer) -> PaginatedResponse[DepartmentOut]:
    items, total = await repo.list_departments(db, page)
    return paginated(
        [DepartmentOut.model_validate(i) for i in items],
        page.page,
        page.page_size,
        total,
        "Departments retrieved.",
    )


@router.get("/departments/{department_id}", response_model=ApiResponse[DepartmentOut])
async def get_department(department_id: int, db: DbDep, _: Viewer) -> ApiResponse[DepartmentOut]:
    department = await get_live(db, Department, department_id)
    if department is None:
        raise NotFound("Department not found.")
    return ok(DepartmentOut.model_validate(department), "Department retrieved.")


@router.post("/departments", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[DepartmentOut])
async def create_department(payload: DepartmentCreate, db: DbDep, actor: Admin) -> ApiResponse[DepartmentOut]:
    return created(
        DepartmentOut.model_validate(await service.create_department(db, payload, actor)),
        "Department created.",
    )


@router.put("/departments/{department_id}", response_model=ApiResponse[DepartmentOut])
async def update_department(
    department_id: int, payload: DepartmentUpdate, db: DbDep, actor: Admin
) -> ApiResponse[DepartmentOut]:
    department = await service.update_department(db, department_id, payload, actor)
    return ok(DepartmentOut.model_validate(department), "Department updated.")


@router.delete("/departments/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_department(department_id: int, db: DbDep, actor: Admin) -> None:
    await service.delete_department(db, department_id, actor)


# --- shifts ---
@router.get("/shifts", response_model=PaginatedResponse[ShiftOut], summary="List shifts")
async def list_shifts(db: DbDep, page: PageDep, _: Viewer) -> PaginatedResponse[ShiftOut]:
    items, total = await repo.list_shifts(db, page)
    return paginated(
        [ShiftOut.model_validate(i) for i in items], page.page, page.page_size, total, "Shifts retrieved."
    )


@router.get("/shifts/{shift_id}", response_model=ApiResponse[ShiftOut])
async def get_shift(shift_id: int, db: DbDep, _: Viewer) -> ApiResponse[ShiftOut]:
    shift = await get_live(db, Shift, shift_id)
    if shift is None:
        raise NotFound("Shift not found.")
    return ok(ShiftOut.model_validate(shift), "Shift retrieved.")


@router.post("/shifts", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[ShiftOut])
async def create_shift(payload: ShiftCreate, db: DbDep, actor: Admin) -> ApiResponse[ShiftOut]:
    return created(ShiftOut.model_validate(await service.create_shift(db, payload, actor)), "Shift created.")


@router.put("/shifts/{shift_id}", response_model=ApiResponse[ShiftOut])
async def update_shift(shift_id: int, payload: ShiftUpdate, db: DbDep, actor: Admin) -> ApiResponse[ShiftOut]:
    return ok(
        ShiftOut.model_validate(await service.update_shift(db, shift_id, payload, actor)), "Shift updated."
    )


@router.delete("/shifts/{shift_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shift(shift_id: int, db: DbDep, actor: Admin) -> None:
    await service.delete_shift(db, shift_id, actor)


# --- holidays ---
@router.get("/holidays", response_model=PaginatedResponse[HolidayOut], summary="List holidays")
async def list_holidays(
    db: DbDep,
    page: PageDep,
    _: Viewer,
    location_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> PaginatedResponse[HolidayOut]:
    items, total = await repo.list_holidays(db, page, location_id, date_from, date_to)
    return paginated(
        [HolidayOut.model_validate(i) for i in items], page.page, page.page_size, total, "Holidays retrieved."
    )


@router.post("/holidays", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[HolidayOut])
async def create_holiday(payload: HolidayCreate, db: DbDep, actor: Admin) -> ApiResponse[HolidayOut]:
    return created(
        HolidayOut.model_validate(await service.create_holiday(db, payload, actor)), "Holiday created."
    )


@router.put("/holidays/{holiday_id}", response_model=ApiResponse[HolidayOut])
async def update_holiday(
    holiday_id: int, payload: HolidayUpdate, db: DbDep, actor: Admin
) -> ApiResponse[HolidayOut]:
    return ok(
        HolidayOut.model_validate(await service.update_holiday(db, holiday_id, payload, actor)),
        "Holiday updated.",
    )


@router.delete("/holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_holiday(holiday_id: int, db: DbDep, actor: Admin) -> None:
    await service.delete_holiday(db, holiday_id, actor)
