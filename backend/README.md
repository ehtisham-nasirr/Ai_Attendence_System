# FaceTrack backend

FastAPI REST API, WebSocket live feed, attendance rules and Celery jobs for FaceTrack (requirements §8, §10.3, §11–§15). The recognition engine (`engine/`) only produces events. Attendance is decided **here only** (standards/02).

## Layout

```
app/
  api/v1/        routers: auth, users, organization, employees, cameras, recognition, attendance, system
  api/internal.py  MediaMTX auth hook (not exposed by Nginx)
  ws/live.py     /ws/live (cookie auth, role-filtered messages)
  schemas/       Pydantic request/response models
  domain/        business rules (attendance/rules.py is pure and fully unit tested)
  repositories/  SQLAlchemy queries; the only place that builds SQL
  services/      engine client, object storage, Redis live channel, MediaMTX, LDAP, SMTP, Teams
  worker/        Celery app, Redis stream consumer, Beat schedule, tasks
  core/          config, DB session/transactions, security (JWT, CSRF, RBAC, data scope), errors, metrics
alembic/         migrations (rev 0001 = full schema, monthly event partitions)
tests/           pytest against real PostgreSQL + Redis
```

The flow is router → schema → domain service → repository. Database models live in `common/facetrack_common/models` because the engine reads the same tables.

## Run locally

Requires Python 3.12, [uv](https://docs.astral.sh/uv/), PostgreSQL 16 with pgvector, and Redis 7.

```bash
cp .env.example .env            # fill every change-me; never commit .env
uv sync
uv run alembic upgrade head
SEED_ADMIN_USERNAME=admin SEED_ADMIN_EMAIL=admin@example.com SEED_ADMIN_PASSWORD='...' \
  uv run python -m app.scripts.seed          # first Super Admin + default settings
uv run uvicorn app.main:create_app --factory --port 8000
uv run celery -A app.worker worker --loglevel=INFO      # also consumes recognition.events
uv run celery -A app.worker beat --loglevel=INFO
```

API docs are at `/api/docs` when `API_DOCS_ENABLED=true` and `ENVIRONMENT` is not `production`. `make gen-api` writes `docs/openapi.yaml`, from which the portal client is generated.

`ENCRYPTION_KEY` must be the same base64 AES-256 key as the engine's `ENGINE_ENCRYPTION_KEY`. Embeddings, snapshots, enrollment photos, LDAP/SMTP secrets in settings and the engine disk buffer all use it (ADR-0001, standards/18).

## Event processing (§10.2, §10.3)

1. The engine `XADD`s to `recognition.events`.
2. A Celery worker bootstep reads the stream as consumer group `backend` and dispatches `process_recognition_event` per message.
3. The task validates the event, inserts it into the partitioned `recognition_events` table (`ON CONFLICT DO NOTHING` on `event_uuid`), and recomputes the employee's work day from all its non-voided events. Because the recomputation is order independent, replayed or late events give the same result (NFR-7).
4. The stream entry is acknowledged only after commit. Unacknowledged entries are reclaimed after 2 minutes. After 10 deliveries, or straight away if malformed, an event moves to `recognition.events.dead` (Q34).
5. Live messages go out on the Redis channel `facetrack.live`. `/ws/live` forwards each one only to users allowed to see it.

## Attendance rules (§10.3)

The rules are in `domain/attendance/rules.py`; the decisions behind them are in `docs/adr/0003` and `docs/open-questions.md` Q10–Q15 and Q33.

- **Work date:** an event belongs to work date D when close(D−1) < t ≤ close(D). Day shifts close at `attendance.day_close_time` (default 02:00); night shifts close at shift end + 240 min.
- **Check-in / check-out:** check-in is the first sighting on an ENTRY or ENTRY_EXIT camera. Check-out is the last later sighting on an EXIT or ENTRY_EXIT camera. Repeats within `attendance.duplicate_cooldown_min` are ignored.
- **Statuses:**
  - Order: Manual > Leave > Holiday/Weekly Off > Absent > Missing Check-out > Half Day > Late > Early Exit > Present.
  - Before the day closes, only Present or Late is shown.
- **Corrections:** an approved correction locks its field, so later events never overwrite it.
- **Approver:** a correction request is approved by one of the employee's department manager, an HR Admin or a Super Admin (ADR-0004).

## Security (§15, standards/06)

- **Sessions and passwords:**
  - Session: a JWT in the HttpOnly `ft_access` cookie, sliding 30 minutes.
  - Double-submit CSRF: the `ft_csrf` cookie must match the `X-CSRF-Token` header on every state-changing request.
  - Passwords: argon2id. The account locks for 30 minutes after 5 failed logins.
  - Login is rate limited in Redis.
- **Active Directory:** optional LDAP bind for users whose `auth_provider` is `ldap`, when `auth.ldap_enabled` is on (FR-40).
- **Access control:**
  - Permissions per role follow §4 (`core/security.py`).
  - Data scope: Department Managers see their departments only; Employees see only their own records.
- **Integrations:** API keys (`X-API-Key`, stored as SHA-256 hashes, with per-key scopes).
- **Audit:** every create, update or delete of attendance, employee, camera, setting, user, correction or biometric data writes `audit_logs` with old and new values.

## Scheduled jobs (Celery Beat, `worker/schedule.py`)

| Job | Every | Purpose |
|---|---|---|
| close-due-days | 10 min | Finalise work days whose close time has passed: Absent, Missing Check-out, Half Day, Early Exit (FR-23) |
| sync-camera-status | 30 s | Poll engine nodes, update camera status, alert when offline > 5 min (FR-3, FR-4) |
| ensure-event-partitions | 6 h | Keep monthly `recognition_events` partitions 3 months ahead |
| trim-event-stream | hourly | Trim acknowledged stream entries |
| retention | hourly | Delete snapshots, unknown faces and events past their retention (FR-39) |
| cleanup-temp-imports | 3 h | Remove abandoned upload temp files |
| scheduled-notifications | 5 min | Daily summary and scheduled report emails (Phase 4) |

Business times come from the `settings` table, so a change takes effect without a restart.

## Tests

```bash
# Fastest: point at an existing PostgreSQL (with pgvector) and Redis
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/facetrack_test \
TEST_REDIS_URL=redis://localhost:6379/14 uv run pytest
# Otherwise testcontainers starts pgvector/pgvector:pg16 and redis:7 (needs Docker)
uv run pytest --cov=app
uv run ruff check . && uv run ruff format --check . && uv run mypy app
```

The tests never use real employee data or real cameras: the engine is replaced by `FakeEngine` (`tests/conftest.py`).
