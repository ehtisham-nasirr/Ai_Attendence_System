# /add-crud-module

Use this to scaffold a full CRUD module (e.g. "add a CRUD for Shift", "add a CRUD for Holiday", "add a CRUD for Department") — model, migration, API and the matching React list + add/edit UI.

## Arguments

`$ARGUMENTS` = the resource name, e.g. `Shift`, `Holiday`, `Department`, `Location`.

## Before Starting

Read `standards/02-backend-architecture.md`, `standards/04-rest-api-standards.md`, `standards/05-database-postgresql.md`, `standards/07-frontend-architecture.md` and `standards/08-frontend-state-and-api-layer.md`. Find the resource in requirements §11 (data model) and §12 (API) — use the columns and endpoints defined there.

## Backend Steps

1. **Model** — add the SQLAlchemy model in `common/facetrack_common/models/` (fields, FKs, unique constraints, indexes, `created_at`/`updated_at`, `deleted_at` for soft delete). Check it against `standards/05-database-postgresql.md`.
2. **Migration** — `alembic revision --autogenerate -m "add <resource>"`; review the script, confirm `downgrade()` works; `alembic upgrade head`.
3. **Schemas** — `<Resource>Create`, `<Resource>Update`, `<Resource>Out`, `<Resource>Filter` (Pydantic v2).
4. **Repository** — `backend/app/repositories/<resource>_repo.py` with list (paginated, filtered, sorted), get, create, update, soft delete.
5. **Domain service** — only if there is real logic beyond plain CRUD (overlap checks, side effects, audit). Audit logging of create/update/delete (FR-37) is always required — use the shared audit helper.
6. **Router** — `backend/app/api/v1/<resources>.py`, registered under `/api/v1/<resources>` (plural, kebab-case, no verbs), with `require_permission(...)` on every route per requirements §4 and `response_model` on every route.
7. **Response shape** — use `ok()` / `created()` / `paginated()` from `core/responses.py`.

## Frontend Steps

1. **Regenerate the API client** — `make gen-api`; do not hand-write request functions.
2. **Hooks** — `src/hooks/use<Resource>s.ts` wrapping the generated calls with TanStack Query (list query, mutations that invalidate the list).
3. **Zod schema** — `src/lib/schemas/<resource>Schema.ts` mirroring backend validation.
4. **Components** — `src/components/<resources>/<Resource>Table.tsx` (shared `DataTable`), `<Resource>Form.tsx` (React Hook Form + Zod, inside a shadcn Dialog/Sheet), using `ConfirmDialog` for delete.
5. **Page/route** — `src/pages/<resources>/<Resource>sPage.tsx`, added to the router with the correct role guard and to the sidebar if it is a top-level screen.

## Tests

- Backend: repository/service tests, API tests for each verb (success, invalid input, 401, 403, 404), migration up/down.
- Frontend: form validation test, table render test with mocked API (MSW).

## Batch Log

Create a batch log file in `batch/` per `CLAUDE.md` §7 (e.g. `batch/2026-10-05_1430_add-shift-crud.md`) — required, not optional.

## Report

Use the Final AI Response Format from `CLAUDE.md`. Explicitly list every new file, migration and endpoint added, and the requirement IDs covered.
