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
- **Leave and holidays:** adding or removing leave recomputes that employee's existing days in the range; a holiday change queues `recompute_date` for each affected date (Q41).
- **Monthly register:** `GET /attendance/register?month=YYYY-MM` returns status letters and row totals per employee in the caller's scope (Q40).
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

## Reports (FR-30, FR-31)

`GET /api/v1/reports/{type}?date_from=&date_to=[&department_id=&employee_id=&status=]` returns a preview: the first 500 rows, plus a summary and chart data for the whole result. Report types:

| Type | Content |
|---|---|
| `daily` | Every attendance day |
| `monthly_register` | One calendar month (the month of `date_from`) |
| `late_arrivals` | Days with late minutes |
| `early_exits` | Days with early minutes |
| `absentee` | Absent days |
| `overtime` | Days with overtime minutes |
| `department_summary` | Totals per department |
| `employee_history` | All days of one employee (`employee_id` is required) |

- **Range:** at most 366 days.
- **Scope:** results follow the caller's data scope.
- **Exports:** add `format=xlsx|pdf` to get `202 {job_id}` (audited as `report.export`). Poll `GET /api/v1/jobs/{job_id}`, then download `GET /api/v1/jobs/{job_id}/file`; only the requesting user can, for 24 hours.
  - Excel has every row (times in each employee's timezone, minutes as h:mm, text that starts with `= + - @` neutralised).
  - PDF stops at 5,000 rows.

**Scheduled emails** (`notifications.report_schedules`, managed on the Reports screen):
- `daily` sends yesterday;
- `weekly` sends last Monday–Sunday, on Mondays;
- `monthly` sends last month, on the 1st.

Each schedule covers the whole organisation or one department. The **daily summary** goes to `notifications.hr_emails` (whole organisation) and to each department manager (their departments). **Check-in confirmation** (FR-33) emails the employee once per work day, only for live events (captured within the last 15 minutes).

## Payroll integration (FR-34, FR-35)

**Pull.** `GET /api/v1/integration/attendance?date=YYYY-MM-DD&page=&page_size=` with header `X-API-Key: ft_…`. Keys are created under Settings › Integration (shown once, stored as SHA-256) with scope `attendance:read`, and are rate-limited per key (`API_KEY_RATE_LIMIT_PER_MINUTE`, default 120).

The endpoint returns only **finalised** days (call it after the day close, default 02:00). Each row contains:
- `employee_code`, `hr_external_id`, `employee_name`, `department_code`;
- `work_date`, `shift_name`, `check_in_at` / `check_out_at` (UTC);
- `worked_minutes`, `late_minutes`, `early_minutes`, `overtime_minutes`;
- `status` (+ `status_letter`), `is_manual`, `finalized_at`, `updated_at`.

**Push** (`integration.payroll_mode = push`). Every day at `integration.payroll_push_time`, and on demand, FaceTrack POSTs to `integration.payroll_webhook_url`:

```
POST {payroll_webhook_url}
Content-Type: application/json
X-FaceTrack-Delivery: <uuid>
X-FaceTrack-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256(PAYROLL_WEBHOOK_SECRET, "<t>." + body)>

{"event": "attendance.finalized", "delivery_id": "...", "reason": "scheduled|manual",
 "generated_at": "...", "days": [<rows as in the pull API>]}
```

- **What is sent:** every finalised day changed since the last successful delivery (watermark on `updated_at`). This includes night shifts that close after the push time, and corrections made after the day closed. Receivers should **upsert by (`employee_code`, `work_date`)**, reject timestamps older than 5 minutes, and compare signatures in constant time (reference: `app.domain.integration.payroll.verify`).
- **Failures:** retried 5 times with exponential backoff (1, 2, 4, 8, 16 minutes); an admin alert follows the last failure.
- **Manual push:** `POST /api/v1/integration/payroll/push[?date=]` (Super Admin) resends one date.

## HR sync (FR-12, FR-24)

Every day at `integration.hr_sync_time` when `integration.hr_sync_enabled` is on, and on demand (`POST /api/v1/integration/hr/sync`). FaceTrack calls `integration.hr_base_url` with `Authorization: Bearer $HR_API_TOKEN`. Responses may be a JSON array, or `{"data": [...], "next": "<url>"}` (pages are followed).

| Request | Fields used |
|---|---|
| `GET /employees` | `employee_code` (match key), `full_name`, `department_code` (FaceTrack department code), `designation`, `email`, `phone`, `status` (`active`/`inactive`), `hr_external_id` or `id` |
| `GET /leaves?from=&to=` (30 days back to 90 ahead) | `id` (or `external_ref`), `employee_code`, `from_date`, `to_date`, `type`, `status` (only `approved`, or no status, is imported) |

- **Employees:** missing fields are left unchanged. An employee absent from the feed is **never** deactivated automatically (Q44); only `status: inactive` deactivates, which also stops recognition.
- **Leave:** HR leave in the window that disappears from the feed is treated as cancelled. Every affected attendance day is recomputed.
- **Logging:** each run is audited (`hr_sync.run`) with counts and the first 100 problems.

**This contract has not been verified against the real HR or payroll system (P6).**
