# FastAPI Coding Standards

## Naming

| Kind | Convention | Example |
|---|---|---|
| Classes / Pydantic schemas / SQLAlchemy models | `PascalCase` | `class AttendanceDay`, `class ShiftCreate` |
| Functions / methods | `snake_case`, verb-first | `async def close_day()`, `def compute_late_minutes()` |
| Variables | `snake_case` | `match_threshold = ...` |
| Constants | `UPPER_CASE` | `MAX_LOGIN_ATTEMPTS = 5` |
| Modules / files | `snake_case.py` | `attendance_rules.py` |
| Router files | plural resource name | `api/v1/employees.py`, `api/v1/cameras.py` |
| Celery tasks | verb_object | `close_day`, `push_payroll`, `process_event` |

Avoid meaningless names (`x`, `data1`, `abc`, `tmp2`) unless the variable has an obvious, very short-lived purpose (e.g. a loop index `i`).

## Async Rules

- Routers, services and repositories in the backend are `async def`.
- **Never call blocking code inside `async def`** — no `time.sleep`, `requests`, synchronous file or CPU-heavy work. Use `httpx.AsyncClient`, `asyncio.sleep`, or move the work to a Celery task.
- CPU-heavy work (report generation, PDF rendering, bulk imports) runs in Celery, not in the request.
- The engine's frame-processing code is **not** async — it runs in dedicated processes (see `standards/17-recognition-engine-cpu.md`). Only the engine's internal API is async.

## Dependencies

- Use `Depends(...)` for the DB session, current user, permission checks and pagination — do not re-implement these inside routers.
- Permission checks use the shared `require_permission("<area>:<action>")` dependency from `core/security.py`.

## General Rules

- One clear responsibility per function/class.
- Prefer explicit over implicit — no "magic" that requires tribal knowledge to understand.
- Keep domain boundaries clean: one domain area does not import another area's repositories directly; it calls that area's service.
- Every router declares `response_model` so the OpenAPI spec (and the generated frontend client) stays accurate.
