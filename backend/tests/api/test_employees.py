"""Employees, enrollment, erasure and leave (FR-7..FR-13, FR-24; standards/14, 18)."""

import io

from conftest import Api, FakeEngine, make_org, make_user
from facetrack_common.constants import UserRole
from facetrack_common.models import AuditLog, Employee, FaceEnrollment
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


def jpeg(width: int = 400, height: int = 400, exif: bool = False) -> bytes:
    image = Image.new("RGB", (width, height), (120, 130, 140))
    out = io.BytesIO()
    if exif:
        exif_data = Image.Exif()
        exif_data[0x010F] = "SecretCameraMaker"
        image.save(out, format="JPEG", exif=exif_data.tobytes())
    else:
        image.save(out, format="JPEG")
    return out.getvalue()


async def _hr(api: Api, db: AsyncSession) -> dict:  # type: ignore[type-arg]
    org = await make_org(db)
    await api.as_user(await make_user(db, UserRole.HR_ADMIN, "hr1"))
    return org


async def _create(api: Api, org: dict, code: str = "ITRC-0142", consent: bool = True) -> dict:  # type: ignore[type-arg]
    body = {
        "employee_code": code,
        "full_name": "Ali Raza",
        "department_id": org["sales"].id,
        "shift_id": org["shift"].id,
        "location_id": org["location"].id,
        "email": "ali@example.com",
    }
    if consent:
        body["consent_signed_at"] = "2026-09-01T09:00:00+05:00"
    response = await api.post("/api/v1/employees", json=body)
    assert response.status_code == 201, response.text
    return response.json()["data"]  # type: ignore[no-any-return]


async def test_fr7_create_list_update_employee(api: Api, db: AsyncSession) -> None:
    org = await _hr(api, db)
    created = await _create(api, org)
    assert created["department_name"] == "Sales" and created["enrolled_photos"] == 0
    listing = await api.get("/api/v1/employees", params={"search": "ali"})
    body = listing.json()
    assert body["pagination"] == {"page": 1, "page_size": 20, "total": 1}
    updated = await api.put(f"/api/v1/employees/{created['id']}", json={"designation": "Engineer"})
    assert updated.json()["data"]["designation"] == "Engineer"


async def test_fr7_employee_code_is_unique_409(api: Api, db: AsyncSession) -> None:
    org = await _hr(api, db)
    await _create(api, org)
    response = await api.post("/api/v1/employees", json={"employee_code": "ITRC-0142", "full_name": "X"})
    assert response.status_code == 409


async def test_invalid_input_422_with_field_errors(api: Api, db: AsyncSession) -> None:
    await _hr(api, db)
    response = await api.post("/api/v1/employees", json={"employee_code": "bad code!", "full_name": ""})
    body = response.json()
    assert response.status_code == 422 and body["success"] is False
    assert {"employee_code", "full_name"} <= set(body["errors"])


async def test_unknown_employee_404(api: Api, db: AsyncSession) -> None:
    await _hr(api, db)
    assert (await api.get("/api/v1/employees/999")).status_code == 404


async def test_roles_without_permission_get_403(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    for role in (UserRole.DEPARTMENT_MANAGER, UserRole.OPERATOR):
        client = await make_api(await make_user(db, role, role.value))
        assert (await client.get("/api/v1/employees")).status_code == 403


async def test_standards18_enrollment_blocked_without_consent(
    api: Api, db: AsyncSession, fake_engine: FakeEngine
) -> None:
    org = await _hr(api, db)
    employee = await _create(api, org, consent=False)
    response = await api.post(
        f"/api/v1/employees/{employee['id']}/faces", files=[("photos", ("a.jpg", jpeg(), "image/jpeg"))]
    )
    assert response.status_code == 422 and "consent_signed_at" in response.json()["errors"]
    assert fake_engine.calls == 0


async def test_fr8_fr9_photos_accepted_and_rejected_with_reasons(
    api: Api, db: AsyncSession, fake_engine: FakeEngine
) -> None:
    org = await _hr(api, db)
    employee = await _create(api, org)
    files = [
        ("photos", ("a.jpg", jpeg(exif=True), "image/jpeg")),
        ("photos", ("b.txt", b"not an image", "image/jpeg")),
    ]
    response = await api.post(f"/api/v1/employees/{employee['id']}/faces", files=files)
    body = response.json()["data"]
    assert response.status_code == 200
    assert [r["accepted"] for r in body["results"]] == [True, False]
    assert body["results"][1]["rejection_reason"] == "invalid_image"
    assert body["enrolled_photos"] == 1 and body["enrollment_complete"] is False
    face = (await db.scalars(select(FaceEnrollment))).one()
    assert face.embedding_dim == 128 and face.model_name == "sface"
    # Stored photo is encrypted on disk and EXIF-free once decrypted (standards/14, 18).
    image = await api.get(f"/api/v1/employees/{employee['id']}/faces/{face.id}/image")
    assert image.headers["content-type"] == "image/jpeg" and image.headers["cache-control"].startswith(
        "no-store"
    )
    assert b"SecretCameraMaker" not in image.content
    fake_engine.reject_reason = "face_too_small"
    rejected = await api.post(
        f"/api/v1/employees/{employee['id']}/faces", files=[("photos", ("c.jpg", jpeg(), "image/jpeg"))]
    )
    assert rejected.status_code == 422
    assert fake_engine.notifications.count("gallery_reload") == 1


async def test_fr10_possible_duplicate_warning(api: Api, db: AsyncSession, fake_engine: FakeEngine) -> None:
    org = await _hr(api, db)
    first = await _create(api, org, "E-1")
    second = await _create(api, org, "E-2")
    same = fake_engine.vector(7)
    fake_engine.next_vectors = [same, same * 0.99 + fake_engine.vector(8) * 0.01]
    await api.post(
        f"/api/v1/employees/{first['id']}/faces", files=[("photos", ("a.jpg", jpeg(), "image/jpeg"))]
    )
    response = await api.post(
        f"/api/v1/employees/{second['id']}/faces", files=[("photos", ("b.jpg", jpeg(), "image/jpeg"))]
    )
    assert response.json()["data"]["results"][0]["possible_duplicates"] == ["E-1"]


async def test_engine_down_is_503(api: Api, db: AsyncSession, fake_engine: FakeEngine) -> None:
    org = await _hr(api, db)
    employee = await _create(api, org)
    fake_engine.available = False
    response = await api.post(
        f"/api/v1/employees/{employee['id']}/faces", files=[("photos", ("a.jpg", jpeg(), "image/jpeg"))]
    )
    assert response.status_code == 503 and response.json()["success"] is False


async def test_fr13_deactivation_reloads_gallery(api: Api, db: AsyncSession, fake_engine: FakeEngine) -> None:
    org = await _hr(api, db)
    employee = await _create(api, org)
    response = await api.put(f"/api/v1/employees/{employee['id']}", json={"status": "inactive"})
    assert response.json()["data"]["deactivated_at"] is not None
    assert "gallery_reload" in fake_engine.notifications


async def test_fr13_biometric_erasure_is_admin_only_confirmed_and_hard(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    org = await make_org(db)
    hr = await make_api(await make_user(db, UserRole.HR_ADMIN, "hr1"))
    admin = await make_api(await make_user(db, UserRole.SUPER_ADMIN, "admin1"))
    employee = await _create(hr, org)
    await hr.post(
        f"/api/v1/employees/{employee['id']}/faces", files=[("photos", ("a.jpg", jpeg(), "image/jpeg"))]
    )
    url = f"/api/v1/employees/{employee['id']}/biometrics"
    assert (await hr.request("DELETE", url, json={"confirm_employee_code": "ITRC-0142"})).status_code == 403
    assert (await admin.request("DELETE", url, json={"confirm_employee_code": "wrong"})).status_code == 422
    assert (
        await admin.request("DELETE", url, json={"confirm_employee_code": "ITRC-0142"})
    ).status_code == 204
    assert await db.scalar(select(func.count()).select_from(FaceEnrollment)) == 0
    entry = (await db.scalars(select(AuditLog).where(AuditLog.action == "employee.biometrics_erase"))).one()
    assert entry.new_values is not None and entry.new_values["enrollments"] == 1
    assert "embedding" not in str(entry.new_values)


async def test_fr13_delete_employee_erases_faces_and_keeps_record(api: Api, db: AsyncSession) -> None:
    org = await _hr(api, db)
    employee = await _create(api, org)
    await api.post(
        f"/api/v1/employees/{employee['id']}/faces", files=[("photos", ("a.jpg", jpeg(), "image/jpeg"))]
    )
    response = await api.delete(
        f"/api/v1/employees/{employee['id']}", params={"confirm_employee_code": "ITRC-0142"}
    )
    assert response.status_code == 204
    assert await db.scalar(select(func.count()).select_from(FaceEnrollment)) == 0
    stored = await db.get(Employee, employee["id"])
    assert stored is not None and stored.deleted_at is not None
    assert (await api.get(f"/api/v1/employees/{employee['id']}")).status_code == 404


async def test_fr11_import_returns_202_and_job(api: Api, db: AsyncSession, no_celery: list) -> None:  # type: ignore[type-arg]
    await _hr(api, db)
    sheet = b"employee_code,full_name\nE-9,Sara Khan\n"
    response = await api.post("/api/v1/employees/import", files={"sheet": ("e.csv", sheet, "text/csv")})
    assert response.status_code == 202
    job_id = response.json()["data"]["job_id"]
    assert no_celery[-1][0].endswith("import_employees")
    job = await api.get(f"/api/v1/jobs/{job_id}")
    assert job.json()["data"]["status"] == "queued"
    bad = await api.post(
        "/api/v1/employees/import", files={"sheet": ("e.exe", b"MZ\x00\x01", "application/octet-stream")}
    )
    assert bad.status_code == 422


async def test_fr24_leave_crud(api: Api, db: AsyncSession) -> None:
    org = await _hr(api, db)
    employee = await _create(api, org)
    bad = await api.post(
        "/api/v1/leaves",
        json={
            "employee_id": employee["id"],
            "from_date": "2026-10-06",
            "to_date": "2026-10-05",
            "type": "annual",
        },
    )
    assert bad.status_code == 422
    created = await api.post(
        "/api/v1/leaves",
        json={
            "employee_id": employee["id"],
            "from_date": "2026-10-05",
            "to_date": "2026-10-06",
            "type": "annual",
        },
    )
    assert created.status_code == 201
    listing = await api.get("/api/v1/leaves", params={"employee_id": employee["id"]})
    assert listing.json()["pagination"]["total"] == 1
    assert (await api.delete(f"/api/v1/leaves/{created.json()['data']['id']}")).status_code == 204
