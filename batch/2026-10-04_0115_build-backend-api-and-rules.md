# Batch: build-backend-api-and-rules

**Date:** 2026-10-04 01:15
**Type:** feature
**Command Used:** commands/new-feature.md (with commands/add-crud-module.md for the CRUD resources)
**Standards Referenced:** standards/01–06, 09, 10, 11, 12, 13, 14, 15, 16, 18
**Requirements:** FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, FR-8, FR-9, FR-10, FR-11, FR-13, FR-19, FR-20, FR-21, FR-22, FR-23, FR-25, FR-26, FR-27, FR-28, FR-29, FR-36, FR-37, FR-38, FR-39, FR-40, NFR-6, NFR-7, NFR-9, NFR-10, NFR-11, NFR-12, §10.2, §10.3, §11, §12, §14, §15

## Summary
Built the FastAPI backend (requirements §16, Phase 3 "Backend"):
- REST API (§12) in the standards/04 envelope (ADR-0002);
- attendance rules engine (§10.3, ADR-0003);
- Celery Redis-stream event consumer with dead-lettering (§10.2);
- WebSocket live feed;
- security: sessions, CSRF, RBAC with data scope, lockout, audit;
- Celery Beat jobs (day close, camera status, partitions, retention);
- Alembic schema for all 16 tables.

## Changes Made
- **Schema:** Alembic rev `0001`. All 16 tables, with `recognition_events` range-partitioned by month (−1..+3 months plus a default partition) and the pgvector extension. Embeddings are stored as AES-256-GCM ciphertext (ADR-0001). The departments↔users FK cycle is resolved with `use_alter`.
- **core/:**
  - settings from env;
  - async DB session and `transaction()` helper;
  - JWT HttpOnly cookie with sliding 30 min and session versioning, double-submit CSRF, argon2id, lockout 5 / 30 min;
  - `Permission` map per §4 and `DataScope` (manager → their departments, employee → self);
  - API keys (SHA-256, scopes);
  - Redis rate limits, request-ID/JSON logging middleware;
  - error envelope handlers, Prometheus metrics.
- **domain/:**
  - `attendance/rules.py` (pure):
    - work-date assignment, including night shifts across midnight;
    - order-independent check-in/out derivation and duplicate cooldown;
    - late, early, half-day, overtime;
    - status precedence;
    - provisional vs. finalised status.
  - `attendance/service.py`: recompute a day from all its events, honouring locked (corrected) fields; day close; manual day.
  - `recognition`:
    - event validation and idempotent insert;
    - void (FR-28) with recompute;
    - unknown-face review, assign (FR-27, re-embedded through the engine) and dismiss;
    - similarity grouping.
  - `employees`:
    - CRUD with history in the audit log;
    - consent gate;
    - photo enrollment (3–10 photos, EXIF strip, engine validation, duplicate-face warning FR-10);
    - Excel/CSV + ZIP import (FR-11);
    - deactivate (gallery reload) and permanent biometric erase (FR-13).
  - `cameras`: CRUD with encrypted RTSP credentials, connection test, MediaMTX live-view token, status from engine nodes, offline alert after 5 min.
  - `corrections` (single approver, ADR-0004; locks the field), `leaves`, `dashboard`, `settings` (validated per key, secrets encrypted and masked), `organization`, `users`, `audit`, `retention`, `auth` (local + LDAP).
- **repositories/:** all SQL, including `attendance_repo.get_or_create_for_update` (row lock) and an `ON CONFLICT DO NOTHING` event insert.
- **api/v1:** 71 operations across auth, users, organization, employees, cameras, recognition, attendance and system. `api/internal.py` is the MediaMTX auth hook. `ws/live.py` serves `/ws/live` with role-filtered messages.
- **worker/:**
  - Celery app with a consumer bootstep (`XREADGROUP` group `backend`, ack after commit, `XAUTOCLAIM` re-dispatch, dead-letter after 10 deliveries);
  - Beat schedule;
  - tasks for events, attendance, cameras, maintenance (partitions, stream trim, retention, temp cleanup), employees, and notifications (stub until Phase 4).
- **scripts:** `seed.py` (first Super Admin from env, default settings) and `export_openapi.py` → `docs/openapi.yaml`. Operation IDs are the route names, for the generated portal client.
- **Packaging:** `backend/Dockerfile` (one image for API, worker, beat and migrate), `.env.example`, README, root `Makefile` targets (`test-backend`, `lint-backend`, `migrate`, `seed`, `gen-api`).
- `docs/open-questions.md`: Q33–Q35 added (no-shift employees, failing events, session timeout); P10 (push blocked).

## Files Changed
```
backend/pyproject.toml, backend/uv.lock, backend/alembic.ini, backend/Dockerfile, backend/README.md, backend/.env.example
backend/alembic/{env.py,script.py.mako}, backend/alembic/versions/20261003_0001_initial_schema.py
backend/app/main.py
backend/app/core/{config,db,security,exceptions,responses,pagination,request_context,redis,ratelimit,crypto,metrics,middleware}.py
backend/app/schemas/{common,auth,user,organization,employee,camera,recognition,attendance,system}.py
backend/app/repositories/{base,user_repo,organization_repo,employee_repo,camera_repo,event_repo,attendance_repo,system_repo}.py
backend/app/services/{storage,engine_client,live,mediamtx,jobs,metrics_store,directory,email,teams}.py
backend/app/domain/{attendance,audit,auth,cameras,corrections,dashboard,employees,leaves,organization,recognition,retention,settings,users}/
backend/app/api/{deps,internal}.py, backend/app/api/v1/{auth,users,organization,employees,cameras,recognition,attendance,system}.py
backend/app/ws/live.py
backend/app/worker/{__init__,celery_app,runtime,schedule,consumer,dispatch}.py, backend/app/worker/tasks/*.py
backend/app/scripts/{seed,export_openapi}.py
backend/tests/** (12 test modules)
docs/openapi.yaml, docs/open-questions.md, Makefile
```

## Database Changes
- New migration `0001` (initial schema). Verified on a fresh database by `tests/migrations/test_migrations.py`: upgrade head, `alembic check` (no model drift), downgrade −1, upgrade again. It was also run by hand against `facetrack_dev` and `facetrack_migrate`.
- Partitions: monthly `recognition_events_YYYY_MM` plus `recognition_events_default`. The `ensure-event-partitions` job keeps 3 months ahead.
- No FK into the partitioned table (Q21).

## CPU / Performance Impact
No engine change. The backend does no image work; enrollment and unknown-face assignment call the engine's `/embed`. Event processing was **not load-tested** at NFR scale (600 employees × 2 events in a 30-minute peak). Only correctness was checked.

## Testing
- **Automated:** 106 backend tests pass against real PostgreSQL 16 + pgvector and Redis 7 (`TEST_DATABASE_URL` / `TEST_REDIS_URL`), with `FakeEngine` in place of the engine. ruff, ruff format and mypy (`app/`, strict) are clean.
  - `domain/test_attendance_rules.py` (28): every §10.3 rule and edge case, including night shift across midnight, grace, half day, overtime, holiday/leave/weekly off with attendance, duplicate cooldown, precedence, exit-camera-only, single ENTRY_EXIT sighting, and order independence.
  - `domain/test_event_processing.py` (13): valid, duplicate `event_uuid`, invalid (rejected), void and recompute, locked corrected fields, day close, unknown faces.
  - `domain/test_camera_status.py` (3): online/offline, unreachable node, disabled camera, offline > 5 min alert.
  - `api/*` (54): success, 422, 401, 403 (role and department scope), 404 and 409 for auth, users, organisation, employees/enrollment/import, cameras/live view, settings, attendance/corrections, recognition and dashboard; also CSRF, lockout, unlock and audit entries.
  - `worker/test_worker.py` (7): stream consumer, ack only after commit, dead-letter, `close_due_days` run twice gives the same result, retention.
  - `migrations/test_migrations.py` (1).
- **Coverage:** 82% of `app/`.
  - rules 99%, attendance service 88%, auth 97%, corrections 92%, employees 92%, organisation 95%, users 92%, retention 100%, camera status 100%, recognition 85%, settings 85%, dashboard 82%.
  - Cameras service is at 64%: the live-view/MediaMTX paths are covered only by the E2E run below.
- **End-to-end on the dev stack** (standards/11 checklist):
  - API (uvicorn :8000) `/health` ok. Engine :8100 `/health` ok with a synthetic camera.
  - The Celery worker and beat ran against `facetrack_dev`, Redis db 5.
  - The camera showed online with runtime stats from the engine.
  - A recognition event XADDed to the stream became an attendance day, and the dashboard showed present = 1.
  - A malformed event went to `recognition.events.dead`.
- **Not verified:**
  - recognition of real faces through enrollment (no consented photos; the engine was given no face images);
  - LDAP against a real Active Directory (P6);
  - SMTP/Teams (P7);
  - the MediaMTX WebRTC live view with a real camera (P5);
  - event throughput at NFR peak load;
  - the Docker image build (Dockerfile written; built in Phase 5).

## Notes
- Clarifications and defaults: ADR-0001 to ADR-0004, Q10–Q35. Q33 (no-shift employees are never auto-Absent) and Q34 (dead-letter policy) are new.
- Libraries beyond CLAUDE.md §1.2 are listed in Q26; `pyyaml` (OpenAPI export only) was added to that list.
- Outside the listed layout (flagged per §0.4): `app/worker/consumer.py` and `app/worker/dispatch.py` (the Celery bootstep and the API-side task sender), and `app/api/internal.py` (MediaMTX hook, not routed by Nginx).
- Fixed in this batch: a leftover line in `api/v1/organization.py` that only kept an unused import alive was removed.
