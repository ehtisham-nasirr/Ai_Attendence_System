"""Employees, face enrollment, biometric erasure, bulk import and leave (FR-7..FR-13, FR-24)."""

import os
import tempfile
from datetime import date
from typing import Annotated

from facetrack_common.constants import EmployeeStatus, EnrollmentSource
from facetrack_common.models import User
from facetrack_common.schemas.envelope import ApiResponse, PaginatedResponse
from fastapi import APIRouter, File, Form, Query, UploadFile, status
from fastapi.responses import Response

from app.api.deps import DbDep, PageDep, jpeg_response
from app.core.config import get_settings
from app.core.exceptions import ValidationFailed
from app.core.responses import created, ok, paginated
from app.core.security import Permission, require_permission
from app.domain.employees import enrollment
from app.domain.employees import service as employee_service
from app.domain.leaves import service as leave_service
from app.domain.settings import service as settings_service
from app.repositories import employee_repo
from app.schemas.employee import (
    BiometricErasure,
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
    EnrollmentResult,
    FaceOut,
    ImportAccepted,
    LeaveCreate,
    LeaveOut,
)
from app.services import jobs
from app.worker.dispatch import start_employee_import

router = APIRouter(tags=["employees"])
HrUser = Annotated[User, require_permission(Permission.EMPLOYEES_MANAGE)]
EraseUser = Annotated[User, require_permission(Permission.BIOMETRICS_ERASE)]


@router.get("/employees", response_model=PaginatedResponse[EmployeeOut], summary="List employees")
async def list_employees(
    db: DbDep,
    page: PageDep,
    _: HrUser,
    search: Annotated[str | None, Query(max_length=100)] = None,
    department_id: int | None = None,
    status_filter: Annotated[EmployeeStatus | None, Query(alias="status")] = None,
    enrolled: bool | None = None,
) -> PaginatedResponse[EmployeeOut]:
    departments = frozenset({department_id}) if department_id else None
    items, total = await employee_repo.list_employees(
        db, page, search=search, department_ids=departments, status=status_filter, enrolled=enrolled
    )
    return paginated(
        await employee_service.to_out(db, items), page.page, page.page_size, total, "Employees retrieved."
    )


@router.get("/employees/{employee_id}", response_model=ApiResponse[EmployeeOut], summary="Get an employee")
async def get_employee(employee_id: int, db: DbDep, _: HrUser) -> ApiResponse[EmployeeOut]:
    employee = await employee_service.get_or_404(db, employee_id)
    return ok((await employee_service.to_out(db, [employee]))[0], "Employee retrieved.")


@router.post("/employees", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[EmployeeOut])
async def create_employee(payload: EmployeeCreate, db: DbDep, actor: HrUser) -> ApiResponse[EmployeeOut]:
    employee = await employee_service.create_employee(db, payload, actor)
    return created((await employee_service.to_out(db, [employee]))[0], "Employee created.")


@router.put("/employees/{employee_id}", response_model=ApiResponse[EmployeeOut])
async def update_employee(
    employee_id: int, payload: EmployeeUpdate, db: DbDep, actor: HrUser
) -> ApiResponse[EmployeeOut]:
    """Setting status to inactive stops recognition immediately (FR-13)."""
    employee = await employee_service.update_employee(db, employee_id, payload, actor)
    return ok((await employee_service.to_out(db, [employee]))[0], "Employee updated.")


@router.delete(
    "/employees/{employee_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an employee and permanently erase their face data",
)
async def delete_employee(
    employee_id: int, db: DbDep, actor: HrUser, confirm_employee_code: Annotated[str, Query(min_length=1)]
) -> None:
    """FR-13: the record is soft-deleted (attendance history stays) and all biometric data is hard-deleted.
    `confirm_employee_code` must equal the employee's code."""
    await employee_service.delete_employee(db, employee_id, confirm_employee_code, actor)


@router.delete(
    "/employees/{employee_id}/biometrics",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Erase all face data of an employee (right to erasure)",
)
async def erase_biometrics(employee_id: int, payload: BiometricErasure, db: DbDep, actor: EraseUser) -> None:
    """Super Admin only. Hard-deletes enrollments, photos, embeddings, event snapshots and assigned
    unknown faces, writes an audit entry (without the data) and reloads the gallery. Body must
    confirm the employee code."""
    await employee_service.erase_employee_biometrics(db, employee_id, payload.confirm_employee_code, actor)


# --- faces ---
@router.get(
    "/employees/{employee_id}/faces", response_model=ApiResponse[list[FaceOut]], summary="Face gallery"
)
async def list_faces(employee_id: int, db: DbDep, _: HrUser) -> ApiResponse[list[FaceOut]]:
    await employee_service.get_or_404(db, employee_id)
    faces = await employee_repo.list_faces(db, employee_id)
    return ok([FaceOut.model_validate(f) for f in faces], "Faces retrieved.")


@router.post(
    "/employees/{employee_id}/faces",
    response_model=ApiResponse[EnrollmentResult],
    summary="Upload enrollment photos (multipart)",
)
async def upload_faces(
    employee_id: int,
    db: DbDep,
    actor: HrUser,
    photos: Annotated[list[UploadFile], File(description="JPEG/PNG, <= 5 MB each, 1-10 files")],
    source: Annotated[str, Form(pattern="^(upload|webcam)$")] = "upload",
) -> ApiResponse[EnrollmentResult]:
    """FR-8/FR-9: each photo is checked (one face, width >= 112 px, quality, blur) and either stored
    or rejected with a reason. Requires recorded consent (422 otherwise); 503 if the engine is down.
    FR-10: `possible_duplicates` lists other employees with a very similar face."""
    if not 1 <= len(photos) <= 10:
        raise ValidationFailed(errors={"photos": ["Upload between 1 and 10 photos."]})
    max_bytes = get_settings().max_photo_mb * 1024 * 1024
    incoming = [
        enrollment.IncomingPhoto(photo.filename or "photo", await photo.read(max_bytes + 1))
        for photo in photos
    ]
    results, count = await enrollment.enroll_photos(
        db, employee_id, incoming, EnrollmentSource(source), actor
    )
    minimum = int((await settings_service.resolved(db))["enrollment.min_photos"])
    body = EnrollmentResult(results=results, enrolled_photos=count, enrollment_complete=count >= minimum)
    if not any(r.accepted for r in results):
        raise ValidationFailed("No photo was accepted.", errors={"photos": [r.model_dump() for r in results]})
    return ok(body, "Photos processed.")


@router.delete("/employees/{employee_id}/faces/{face_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_face(employee_id: int, face_id: int, db: DbDep, actor: HrUser) -> None:
    await enrollment.delete_face(db, employee_id, face_id, actor)


@router.get(
    "/employees/{employee_id}/faces/{face_id}/image", response_class=Response, summary="Enrollment photo"
)
async def face_image(
    employee_id: int, face_id: int, db: DbDep, _: HrUser, thumbnail: bool = False
) -> Response:
    return jpeg_response(await enrollment.face_image(db, employee_id, face_id, thumbnail))


@router.get(
    "/employees/{employee_id}/photo", response_class=Response, summary="Best enrollment photo (thumbnail)"
)
async def employee_photo(employee_id: int, db: DbDep, _: HrUser) -> Response:
    return jpeg_response(await enrollment.face_image(db, employee_id, None, thumbnail=True))


# --- bulk import (FR-11) ---
@router.post(
    "/employees/import",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[ImportAccepted],
    summary="Bulk import employees (Excel/CSV) and photos (ZIP named by employee code)",
)
async def import_employees(
    db: DbDep,
    actor: HrUser,
    sheet: Annotated[UploadFile, File(description="XLSX or CSV, <= 10 MB")],
    photos_zip: Annotated[
        UploadFile | None, File(description="ZIP of <employee_code>/<n>.jpg, <= 200 MB")
    ] = None,
) -> ApiResponse[ImportAccepted]:
    """Runs in the background (202). Poll `GET /jobs/{job_id}` for the per-row result."""
    settings = get_settings()
    sheet_data = await sheet.read(settings.max_import_mb * 1024 * 1024 + 1)
    if len(sheet_data) > settings.max_import_mb * 1024 * 1024:
        raise ValidationFailed(errors={"sheet": [f"The file is larger than {settings.max_import_mb} MB."]})
    if not (sheet_data.startswith(b"PK") or _looks_like_csv(sheet_data)):
        raise ValidationFailed(errors={"sheet": ["Upload an .xlsx or .csv file."]})
    upload_dir = settings.media_root / "tmp-imports"
    upload_dir.mkdir(parents=True, exist_ok=True)
    sheet_path = _write_temp(upload_dir, sheet_data, ".xlsx" if sheet_data.startswith(b"PK") else ".csv")
    zip_path = None
    if photos_zip is not None:
        zip_data = await photos_zip.read(settings.max_zip_mb * 1024 * 1024 + 1)
        if len(zip_data) > settings.max_zip_mb * 1024 * 1024 or not zip_data.startswith(b"PK"):
            raise ValidationFailed(
                errors={"photos_zip": [f"Upload a ZIP file of at most {settings.max_zip_mb} MB."]}
            )
        zip_path = _write_temp(upload_dir, zip_data, ".zip")
    job_id = await jobs.create_job("employee_import", actor.id)
    start_employee_import(job_id, sheet_path, zip_path, actor.id)
    return ok(ImportAccepted(job_id=job_id), "Import started.")


def _looks_like_csv(data: bytes) -> bool:
    try:
        head = data[:2048].decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    return "," in head and "\x00" not in head


def _write_temp(directory: os.PathLike[str], data: bytes, suffix: str) -> str:
    fd, path = tempfile.mkstemp(dir=directory, suffix=suffix)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    return path


# --- leave (FR-24, Q30) ---
@router.get("/leaves", response_model=PaginatedResponse[LeaveOut], summary="List leave")
async def list_leaves(
    db: DbDep,
    page: PageDep,
    _: HrUser,
    employee_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> PaginatedResponse[LeaveOut]:
    items, total = await employee_repo.list_leaves(db, page, employee_id, date_from, date_to)
    return paginated(
        [LeaveOut.model_validate(i) for i in items], page.page, page.page_size, total, "Leave retrieved."
    )


@router.post("/leaves", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[LeaveOut])
async def create_leave(payload: LeaveCreate, db: DbDep, actor: HrUser) -> ApiResponse[LeaveOut]:
    return created(
        LeaveOut.model_validate(await leave_service.create_leave(db, payload, actor)), "Leave added."
    )


@router.delete("/leaves/{leave_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_leave(leave_id: int, db: DbDep, actor: HrUser) -> None:
    await leave_service.delete_leave(db, leave_id, actor)
