# Business Logic, Duplication & Refactoring

## Single Source of Truth for Business Rules

Every business rule has **one authoritative implementation**:

| Rule | Lives in | Never in |
|---|---|---|
| Attendance rules (check-in/out, late, early exit, half day, overtime, night shift, day close, precedence) | `backend/app/domain/attendance/` | engine, frontend, routers, Celery tasks, SQL views |
| Corrections and approvals | `backend/app/domain/corrections/` | frontend |
| Enrollment rules (consent, duplicate warning, photo acceptance) | `backend/app/domain/employees/` (photo quality via engine `/embed`) | frontend |
| Recognition decision (threshold, margin, voting, liveness) | `engine/app/pipeline/` with values from `settings` | backend, frontend |
| Recognition-event shape | `common/facetrack_common/events.py` | anywhere else |
| Permissions and data scope | `backend/app/core/security.py` | frontend (UI may hide, never decides) |

```
Business Rule
      ↓
Backend domain service (or engine pipeline for recognition)
      ↓
     API
      ↓
  Frontend (displays results)
```

The frontend may mirror a rule for UX (e.g. disable "Approve" for a user without permission), but the backend remains authoritative. The frontend never calculates attendance status, worked hours or late minutes — it displays the values the API returns.

Thresholds, cooldowns, grace periods, retention periods and FPS limits are **configuration**, read from the `settings` table or per-camera/per-shift columns — never duplicated as constants in code.

## Duplication

Before creating a new:

- Component or hook
- Domain service function or repository query
- Pydantic schema or SQLAlchemy model
- Utility (date/time, formatting, encryption)
- API endpoint
- Celery task

**search the project first**, including `common/`. If something equivalent exists, reuse or extend it instead of writing a parallel version. Schemas and models needed by both engine and backend go in `common/`, never copied.

## Refactoring Rule

When fixing a bug, apply the smallest change that correctly fixes it, in this order of preference:

1. **First preference:** the smallest safe change.
2. **Second preference:** refactor the affected area *only if* the existing structure prevents a correct fix.
3. **Third preference:** larger architectural changes — only when explicitly requested or clearly unavoidable.

Do not turn "fix the late-minutes calculation" into "rewrite the attendance engine."
