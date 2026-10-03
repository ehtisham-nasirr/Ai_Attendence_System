# Backend Architecture (FastAPI)

## Responsibility Separation

```
HTTP request
  ↓
Router (app/api/v1/*.py)         ← auth + permission dependencies, request/response schemas
  ↓
Pydantic schema                  ← input validation, output shape
  ↓
Domain service (app/domain/*)    ← business rules, transactions, multi-step logic
  ↓
Repository (app/repositories/*)  ← SQLAlchemy queries
  ↓
PostgreSQL
```

Background and event flows use the **same domain services**:

```
Engine → Redis Stream "recognition.events" → Celery task process_event → domain service → repository → PostgreSQL
Celery Beat schedule → Celery task (close_day, sync_hr, push_payroll, retention) → domain service → ...
```

Every layer has one job. Never let a router, Celery task or WebSocket handler contain business logic or raw queries.

## Routers

Routers should only:

- Declare the path, method, status code and response model
- Inject dependencies (`db session`, `current_user`, `require_permission(...)`)
- Pass the validated schema to a domain service
- Wrap the result in the standard response envelope (`core/responses.py`)

A router function should read like a short checklist, not a workflow.

```python
# app/api/v1/shifts.py
@router.post("", status_code=201, response_model=ApiResponse[ShiftOut])
async def create_shift(
    payload: ShiftCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("settings:manage")),
) -> ApiResponse[ShiftOut]:
    shift = await shift_service.create_shift(db, payload, actor=user)
    return ok(shift, "Shift created successfully.")
```

## Schemas (Pydantic v2)

Schemas handle input validation, output formatting and field-level rules. Naming: `<Resource>Create`, `<Resource>Update`, `<Resource>Out`, `<Resource>Filter`. Cross-record checks (duplicates, overlapping shifts, permission-dependent rules) belong in the domain service, not in validators.

## Domain Services (`app/domain/<area>/service.py`)

Use domain services for:

- Business logic (attendance rules, corrections, enrollment rules)
- Multi-step operations and transactions
- Operations involving multiple tables
- Calling infrastructure services (engine client, storage, HR/payroll)
- Writing audit log entries for every create/update/delete (FR-37)

```python
# app/domain/corrections/service.py
async def approve_correction(db: AsyncSession, correction_id: int, actor: User) -> Correction:
    """Applies an approved correction to the attendance day and records the audit trail."""
    async with db.begin():
        correction = await correction_repo.get_for_update(db, correction_id)
        ensure_can_approve(actor, correction)          # raises PermissionDenied
        await attendance_repo.apply_correction(db, correction)
        await audit_service.record(db, actor, "correction.approve", correction)
    return correction
```

## Repositories (`app/repositories/`)

Repositories contain SQLAlchemy queries only — no business decisions. One repository per aggregate (`employee_repo`, `attendance_repo`, `camera_repo` ...). See `standards/05-database-postgresql.md`.

## Celery Tasks (`app/worker/tasks/`)

- A task is a thin wrapper: load inputs → call a domain service → log the outcome.
- Every task MUST be **idempotent** (safe to run twice). `process_event` de-duplicates on `event_uuid`; `close_day` can be re-run for a date without double-marking.
- Use retries with backoff for external calls (HR/payroll); never retry forever.
- Scheduled jobs are defined only in the Celery Beat schedule (`worker/schedule.py`), with times read from settings.

## Event Consumer

- The recognition-event schema is defined once in `common/facetrack_common/events.py`. The backend validates every event against it and rejects (logs + dead-letters) invalid ones.
- Consume `recognition.events` with a Redis consumer group so events are acknowledged only after they are committed.

## WebSockets (`app/ws/`)

- `/ws/live` authenticates with the same JWT cookie and applies the same role scoping as the REST API.
- Handlers only forward messages published on Redis Pub/Sub; they never query or compute business data themselves.

## Models

SQLAlchemy models live in `common/` and contain fields, relationships, constraints and simple helper properties. No workflows in models.
