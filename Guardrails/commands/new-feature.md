# /new-feature

Use this when adding a feature that spans backend + frontend, and possibly the engine (e.g. "add the unknown-face review screen", "add the monthly register export", "add payroll webhook retries").

## Before Starting

1. Read `CLAUDE.md` (mandatory rules, AI must-not list, non-negotiable constraints).
2. Read `standards/16-change-management-and-workflow.md` — this command follows that workflow exactly.
3. Read `standards/02-backend-architecture.md` and `standards/07-frontend-architecture.md`.
4. Find the feature's requirement IDs in `docs/requirements.md`.
5. If the feature touches biometric data, also read `standards/18-privacy-and-biometric-data.md`. If it touches the engine, also follow `commands/engine-change.md` for that part.

## Steps

For `$ARGUMENTS` (a short description of the feature):

1. **Understand the requirement.** Restate it in your own words with its FR/NFR IDs. If anything is ambiguous or could change business behaviour, ask before proceeding (`CLAUDE.md` rule #17).
2. **Inspect the existing project.** Find the domain area (`backend/app/domain/<area>/`) and frontend feature folder it belongs to.
3. **Search for reuse.** Check `common/`, `backend/app/domain/`, `backend/app/repositories/`, `backend/app/core/`, and `frontend/src/{hooks,components/common,lib}`. Do not duplicate — see `standards/15-business-logic-and-duplication.md`.
4. **Design the minimal layer set** (per `standards/16-change-management-and-workflow.md` § When Adding a New Feature).
5. **Backend:**
   - Model in `common/` + Alembic migration (only if new data is stored)
   - Schemas
   - Repository queries
   - Domain service (business logic, transaction, audit log)
   - Router (thin, permission dependency, `response_model`)
   - Celery task if the work is heavy or scheduled (idempotent)
   - WebSocket message type only if live updates are required (flag it — it's a contract change)
6. **Frontend:**
   - `make gen-api`
   - Hook(s) with TanStack Query
   - Components/page composed from small pieces, with loading/empty/error states
7. **Tests:** at minimum a success case, an invalid-input case, an unauthorized/forbidden case, and the business rules involved (`standards/11-testing.md`).
8. **Run migrations, start the stack (`make dev`), and check the new flow end to end.**
9. **Create a batch log file in `batch/`** per `CLAUDE.md` §7 — required, even for a small feature.
10. **Report back** using the Final AI Response Format in `CLAUDE.md`.

Do not touch unrelated files. Do not restructure the project to "make room" for this feature unless the existing structure genuinely cannot support it — flag that instead of doing it silently.
