# Testing Standards

## Tools

| Area | Tools |
|---|---|
| Backend + common | Pytest, pytest-asyncio, httpx `AsyncClient`, testcontainers (PostgreSQL, Redis) |
| Engine | Pytest with recorded video clips and labelled face sets (never live cameras) |
| Frontend | Vitest + React Testing Library, MSW for mocked API |
| End-to-end | Playwright |

## What to Test

**Backend:**
- Domain service tests — every attendance rule and edge case in requirements §10.3 (late, early exit, half day, overtime, night shift crossing midnight, holidays, approved leave, duplicate suppression, precedence)
- API tests — success, invalid input, unauthorized, forbidden (wrong role / wrong department scope), not found
- Event consumer tests — valid event, invalid event (dead-lettered), duplicate `event_uuid` (ignored)
- Celery task tests — idempotency (running `close_day` twice gives the same result)
- Migration tests — `alembic upgrade head` and `downgrade -1` on a fresh database

**Engine:**
- Unit tests for motion gate, quality scoring, best-crop selection, voting and threshold/margin logic
- Camera mode state machine transitions (IDLE → ACTIVE → COOLDOWN → IDLE, PAUSED)
- Degradation ladder (force high load and check steps down and back up)
- Accuracy evaluation with `scripts/evaluate.py` (TAR/FAR) when models, thresholds or pipeline change
- CPU benchmark with `scripts/benchmark_cpu.py` when the pipeline changes (see `commands/engine-change.md`)

**Frontend:**
- Component tests for forms, tables, status badges and confirm dialogs
- Hook tests with mocked API (MSW), including error and empty states
- Live feed hook: message handling and reconnect

At minimum, cover: success, invalid input, unauthorized access, not-found, important business rules, edge cases. Test names reference requirement IDs where applicable (`test_fr22_late_after_grace_period`).

**Never modify a test just to make failing code appear successful.** If a test fails, fix the code (or, if the test itself was wrong, say so explicitly and explain why before changing it). **Never relax an accuracy test threshold** to make a model change pass.

## Before Declaring a Task Complete

Verify, and say plainly which of these were actually checked:

1. Backend starts successfully (`make dev`), and `/health` returns OK.
2. Frontend starts and builds (`npm run build`) without type errors.
3. Engine starts against a sample video and reaches ACTIVE mode on motion (if the engine was touched).
4. Modified API endpoints work and the OpenAPI spec/generated client are up to date.
5. Alembic migrations run cleanly up and down.
6. Existing functionality still works (no regressions); relevant tests pass.
7. Ruff, mypy, ESLint and TypeScript checks pass.
8. For engine changes: CPU impact measured and accuracy not reduced.
9. No credentials, face images or embeddings were exposed or committed.
10. No unnecessary files were changed.

If something could not be tested (e.g. no access to real cameras or the data center server), **explicitly say so** — never imply it was verified when it wasn't.
