# Change Management & AI Workflow

## Change Impact Analysis

Before making a significant change, identify:

- Affected requirement IDs (FR/NFR/AC) in `docs/requirements.md`
- Affected `common/` models, schemas or the event contract (these affect **both** engine and backend)
- Affected engine modules and CPU budget
- Affected backend routers, domain services, repositories, Celery tasks
- Affected database tables and migrations
- Affected API endpoints and the generated frontend client
- Affected frontend pages and components
- Affected tests
- Backward-compatibility issues (API consumers, payroll integration, stored events)

Do not modify unrelated parts of the application while you're in there "cleaning up."

## Standard AI Coding Workflow

For every development request:

1. Understand the requirement and find its requirement IDs.
2. Inspect the existing project structure.
3. Locate related code in `common/`, `engine/`, `backend/`, `frontend/`.
4. Identify existing reusable functionality.
5. Determine the smallest safe implementation.
6. Implement the change.
7. Create/review Alembic migrations if models changed.
8. Regenerate the frontend API client if the API changed (`make gen-api`).
9. Add or update tests.
10. Run tests, lint and type checks (and the CPU benchmark for engine changes).
11. Review for security, privacy and regressions.
12. Create the batch log and give the summary (`CLAUDE.md` §6–§7).

## When Modifying Existing Code

Always preserve, unless the requested change explicitly targets it:

- Existing functionality and business rules
- Existing API behaviour and the event contract
- Existing permissions and data scoping
- Existing database relationships
- Existing UI behaviour and validations
- Existing recognition thresholds and voting rules

If a change might affect existing functionality, **say so and flag the risk before proceeding**.

## When Adding a New Feature

A feature generally flows through these layers, top to bottom:

```
Requirement (FR/NFR IDs)
    ↓
SQLAlchemy model (common/)
    ↓
Alembic migration (backend/alembic/)
    ↓
Pydantic schemas (common/ or backend/)
    ↓
Repository (backend/app/repositories/)
    ↓
Domain service (backend/app/domain/)
    ↓
Router (backend/app/api/v1/) + permission dependency
    ↓
Regenerate API client (frontend/src/api/generated/)
    ↓
Hook (frontend/src/hooks/)
    ↓
Components / Page (frontend/src/components, pages)
    ↓
Tests
```

Features that involve recognition (new camera behaviour, new event fields) also go through `commands/engine-change.md`. Not every feature needs every layer — a read-only report may skip the model and migration steps.
