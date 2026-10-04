"""Cameras (FR-1..FR-6), live-view auth, settings (FR-38), organisation CRUD, users (§4)."""

import json

from conftest import Api, FakeEngine, make_org, make_user
from facetrack_common.constants import UserRole
from facetrack_common.models import AuditLog, Camera, Setting
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_async_redis


async def _admin(api: Api, db: AsyncSession) -> dict:  # type: ignore[type-arg]
    org = await make_org(db)
    await api.as_user(await make_user(db, UserRole.SUPER_ADMIN, "admin1"))
    return org


async def test_fr1_camera_credentials_encrypted_and_never_returned(
    api: Api, db: AsyncSession, fake_engine: FakeEngine
) -> None:
    org = await _admin(api, db)
    response = await api.post(
        "/api/v1/cameras",
        json={
            "name": "Main entrance",
            "location_id": org["location"].id,
            "role": "ENTRY",
            "rtsp_url": "rtsp://admin:Sup3rSecret@10.0.0.5:554/Streaming/101",
            "substream_url": "rtsp://admin:Sup3rSecret@10.0.0.5:554/Streaming/102",
            "roi_polygon": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9]],
            "liveness_enabled": True,
        },
    )
    assert response.status_code == 201
    body = response.text
    assert "Sup3rSecret" not in body and "admin" not in response.json()["data"]["stream_host"]
    assert (
        response.json()["data"]["stream_host"] == "10.0.0.5:554" and response.json()["data"]["has_substream"]
    )
    stored = (await db.scalars(select(Camera))).one()
    assert b"Sup3rSecret" not in stored.rtsp_url_encrypted
    assert "cameras_sync" in fake_engine.notifications


async def test_camera_validation_and_conflicts(api: Api, db: AsyncSession) -> None:
    org = await _admin(api, db)
    base = {
        "name": "Cam",
        "location_id": org["location"].id,
        "role": "GENERAL",
        "rtsp_url": "rtsp://10.0.0.9/1",
    }
    assert (await api.post("/api/v1/cameras", json=base)).status_code == 201
    assert (await api.post("/api/v1/cameras", json=base)).status_code == 409
    bad_roi = await api.post(
        "/api/v1/cameras", json={**base, "name": "Cam2", "roi_polygon": [[0, 0], [2, 2]]}
    )
    assert bad_roi.status_code == 422
    bad_url = await api.post("/api/v1/cameras", json={**base, "name": "Cam3", "rtsp_url": "http://x"})
    assert bad_url.status_code == 422
    bad_node = await api.post("/api/v1/cameras", json={**base, "name": "Cam4", "engine_node": "node-9"})
    assert bad_node.status_code == 422


async def test_fr2_test_camera_and_fr3_runtime_in_list(api: Api, db: AsyncSession) -> None:
    org = await _admin(api, db)
    camera = (
        await api.post(
            "/api/v1/cameras",
            json={
                "name": "Cam",
                "location_id": org["location"].id,
                "role": "ENTRY",
                "rtsp_url": "rtsp://10.0.0.9/1",
            },
        )
    ).json()["data"]
    tested = await api.post(f"/api/v1/cameras/{camera['id']}/test")
    assert tested.json()["data"]["ok"] is True and tested.json()["data"]["width"] == 1920
    await get_async_redis().set(
        f"camera_runtime:{camera['id']}",
        json.dumps(
            {
                "mode": "ACTIVE",
                "connected": True,
                "fps_target": 4.0,
                "fps_actual": 3.6,
                "lag_seconds": 0.04,
                "faces_today": 12,
                "last_error": None,
                "updated_at": "2026-10-05T04:00:00+00:00",
            }
        ),
    )
    listing = await api.get("/api/v1/cameras")
    assert listing.json()["data"][0]["runtime"]["mode"] == "ACTIVE"


async def test_live_view_token_is_checked_by_internal_auth(api: Api, db: AsyncSession) -> None:
    org = await _admin(api, db)
    camera = (
        await api.post(
            "/api/v1/cameras",
            json={
                "name": "Cam",
                "location_id": org["location"].id,
                "role": "ENTRY",
                "rtsp_url": "rtsp://10.0.0.9/1",
            },
        )
    ).json()["data"]
    live = (await api.get(f"/api/v1/cameras/{camera['id']}/live")).json()["data"]
    assert live["webrtc_url"] == f"/webrtc/cam-{camera['id']}/whep"
    path = f"cam-{camera['id']}"
    allowed = await api.post(
        "/internal/mediamtx/auth", json={"action": "read", "path": path, "query": f"token={live['token']}"}
    )
    assert allowed.status_code == 200
    other = await api.post(
        "/internal/mediamtx/auth", json={"action": "read", "path": "cam-999", "token": live["token"]}
    )
    publish = await api.post(
        "/internal/mediamtx/auth", json={"action": "publish", "path": path, "token": live["token"]}
    )
    missing = await api.post("/internal/mediamtx/auth", json={"action": "read", "path": path})
    assert (other.status_code, publish.status_code, missing.status_code) == (401, 401, 401)


async def test_live_view_forbidden_for_managers(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    await make_org(db)
    manager = await make_api(await make_user(db, UserRole.DEPARTMENT_MANAGER, "mgr"))
    assert (await manager.get("/api/v1/cameras/1/live")).status_code == 403


async def test_fr38_settings_validation_secrets_and_audit(
    api: Api, db: AsyncSession, fake_engine: FakeEngine
) -> None:
    await _admin(api, db)
    items = {i["key"]: i for i in (await api.get("/api/v1/settings")).json()["data"]}
    assert items["recognition.margin"]["value"] == 0.08 and items["notifications.teams_webhook_url"]["secret"]
    bad = await api.put("/api/v1/settings", json={"values": {"recognition.margin": "lots", "nope.key": 1}})
    assert bad.status_code == 422 and {"recognition.margin", "nope.key"} <= set(bad.json()["errors"])
    ok = await api.put(
        "/api/v1/settings",
        json={
            "values": {
                "recognition.margin": 0.1,
                "notifications.teams_webhook_url": "https://example.com/hook/abc",
            }
        },
    )
    assert ok.status_code == 200
    updated = {i["key"]: i for i in ok.json()["data"]}
    assert updated["recognition.margin"]["value"] == 0.1
    assert updated["notifications.teams_webhook_url"]["value"] == "********"
    stored = (await db.scalars(select(Setting).where(Setting.key == "notifications.teams_webhook_url"))).one()
    assert "example.com" not in json.dumps(stored.value)
    assert "cameras_sync" in fake_engine.notifications  # recognition settings changed


async def test_settings_admin_only(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    hr = await make_api(await make_user(db, UserRole.HR_ADMIN, "hr"))
    assert (await hr.get("/api/v1/settings")).status_code == 403
    assert (await hr.get("/api/v1/audit-logs")).status_code == 403


async def test_fr21_organisation_crud_and_audit(api: Api, db: AsyncSession) -> None:
    await _admin(api, db)
    shift = await api.post(
        "/api/v1/shifts",
        json={"name": "Evening", "start_time": "14:00", "end_time": "22:00", "weekly_offs": [7, 7, 6]},
    )
    assert shift.status_code == 201 and shift.json()["data"]["weekly_offs"] == [6, 7]
    assert (
        await api.post("/api/v1/shifts", json={"name": "Evening", "start_time": "14:00", "end_time": "22:00"})
    ).status_code == 409
    bad_tz = await api.post("/api/v1/locations", json={"name": "Dubai", "timezone": "Mars/Base"})
    assert bad_tz.status_code == 422
    dubai = await api.post("/api/v1/locations", json={"name": "Dubai", "timezone": "Asia/Dubai"})
    holiday = await api.post(
        "/api/v1/holidays",
        json={"location_id": dubai.json()["data"]["id"], "date": "2026-12-02", "name": "National Day"},
    )
    assert holiday.status_code == 201
    logs = (await api.get("/api/v1/audit-logs", params={"entity": "holiday"})).json()
    assert logs["data"][0]["action"] == "holiday.create" and logs["data"][0]["user_name"] == "admin1"
    assert (await api.delete(f"/api/v1/shifts/{shift.json()['data']['id']}")).status_code == 204


async def test_users_crud_and_self_protection(api: Api, db: AsyncSession) -> None:
    await _admin(api, db)
    weak = await api.post(
        "/api/v1/users",
        json={
            "name": "HR",
            "username": "hr2",
            "email": "hr2@example.com",
            "role": "hr_admin",
            "password": "short",
        },
    )
    assert weak.status_code == 422
    created = await api.post(
        "/api/v1/users",
        json={
            "name": "HR",
            "username": "hr2",
            "email": "hr2@example.com",
            "role": "hr_admin",
            "password": "Long-enough-123",
        },
    )
    assert created.status_code == 201 and "password" not in created.json()["data"]
    employee_without_link = await api.post(
        "/api/v1/users",
        json={
            "name": "E",
            "username": "e1",
            "email": "e1@example.com",
            "role": "employee",
            "password": "Long-enough-123",
        },
    )
    assert employee_without_link.status_code == 422
    me = (await api.get("/api/v1/auth/me")).json()["data"]
    assert (await api.delete(f"/api/v1/users/{me['id']}")).status_code == 422
    assert (await api.put(f"/api/v1/users/{me['id']}", json={"role": "hr_admin"})).status_code == 422


async def test_q63_stream_urls_for_camera_managers_only_and_audited(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    org = await make_org(db)
    admin = await make_api(await make_user(db, UserRole.SUPER_ADMIN, "admin1"))
    created = await admin.post(
        "/api/v1/cameras",
        json={
            "name": "Reception",
            "location_id": org["location"].id,
            "role": "ENTRY_EXIT",
            "rtsp_url": "rtsp://admin:Sup3r%40Secret@10.0.0.5:554/cam/realmonitor?channel=1&subtype=0",
            "substream_url": "rtsp://admin:Sup3r%40Secret@10.0.0.5:554/cam/realmonitor?channel=1&subtype=1",
        },
    )
    camera_id = created.json()["data"]["id"]
    response = await admin.get(f"/api/v1/cameras/{camera_id}/stream-urls")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["data"] == {
        "rtsp_url": "rtsp://admin:Sup3r%40Secret@10.0.0.5:554/cam/realmonitor?channel=1&subtype=0",
        "substream_url": "rtsp://admin:Sup3r%40Secret@10.0.0.5:554/cam/realmonitor?channel=1&subtype=1",
    }
    audit = (await db.scalars(select(AuditLog).where(AuditLog.action == "camera.view_stream_urls"))).one()
    assert audit.entity_id == str(camera_id) and "Sup3r" not in str(audit.new_values)
    # The list and detail responses still never carry credentials.
    assert "Sup3r" not in (await admin.get(f"/api/v1/cameras/{camera_id}")).text
    assert (await admin.get("/api/v1/cameras/999/stream-urls")).status_code == 404
    hr = await make_api(await make_user(db, UserRole.HR_ADMIN, "hr"))
    assert (await hr.get(f"/api/v1/cameras/{camera_id}/stream-urls")).status_code == 403
