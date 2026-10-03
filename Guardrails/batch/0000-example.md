# Batch: example-template (delete this file once you've seen the format)

**Date:** 2026-10-05 14:30
**Type:** crud-module
**Command Used:** commands/add-crud-module.md
**Standards Referenced:** standards/02-backend-architecture.md, standards/04-rest-api-standards.md, standards/05-database-postgresql.md, standards/07-frontend-architecture.md
**Requirements:** FR-21, FR-38

## Summary
Added a full CRUD module for `Shift` — model, migration, API and list/add/edit UI in Settings → Shifts.

## Changes Made
- Added `Shift` model in `common/` with `name`, `start_time`, `end_time`, `grace_in_min`, `grace_out_min`, `half_day_pct`, `is_night_shift`, `weekly_offs`.
- Added Alembic migration creating the `shifts` table with a unique constraint on `name`.
- Added `ShiftCreate` / `ShiftUpdate` / `ShiftOut` / `ShiftFilter` schemas and `shift_repo`.
- Added `shift_service` with an overlap check for night shifts and audit logging.
- Added router `/api/v1/shifts` (GET list/detail, POST, PUT, DELETE) guarded by `settings:manage`.
- Regenerated the frontend API client; added `useShifts` hook, `ShiftTable`, `ShiftForm` and `ShiftsPage` under Settings.

## Files Changed
```
common/facetrack_common/models/shift.py
backend/alembic/versions/20261005_1420_add_shifts.py
backend/app/api/v1/shifts.py
backend/app/domain/shifts/service.py
backend/app/repositories/shift_repo.py
backend/app/schemas/shift.py
backend/tests/api/test_shifts.py
frontend/src/api/generated/*            (regenerated)
frontend/src/hooks/useShifts.ts
frontend/src/lib/schemas/shiftSchema.ts
frontend/src/components/shifts/ShiftTable.tsx
frontend/src/components/shifts/ShiftForm.tsx
frontend/src/pages/settings/ShiftsPage.tsx
```

## Database Changes
Migration `20261005_1420_add_shifts` — creates `shifts`. Applied with `alembic upgrade head`; `alembic downgrade -1` tested.

## CPU / Performance Impact
N/A (no engine change).

## Testing
- `pytest backend/tests/api/test_shifts.py` — success, invalid input, 401, 403, 404 cases pass.
- `npm run test -- ShiftForm` — validation tests pass; `npm run build` passes.
- Manually created, edited and deleted a shift in the local portal.
- Not tested against production data volume.

## Notes
Nothing outside `standards/`/`commands/` was needed for this change.
