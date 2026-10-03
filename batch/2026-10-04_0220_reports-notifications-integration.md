# Batch: reports-notifications-integration

**Date:** 2026-10-04 02:20
**Type:** feature
**Command Used:** commands/new-feature.md
**Standards Referenced:** standards/02, 03, 04, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 18
**Requirements:** FR-12, FR-24, FR-30, FR-31, FR-32, FR-33, FR-34, FR-35, FR-37, FR-40; §12 (`/reports/{type}`, `/integration/attendance`, outbound webhook); §13 screen 12, screen 13 (Integration tab)

## Summary
Built requirements §16 Phase 5 ("Reports, notifications and integration"), which is Phase 4 of this build:
- all eight FR-30 reports, with Excel/PDF export through Celery jobs;
- the daily summary, scheduled report emails and check-in confirmation;
- API keys and the payroll pull API, plus a signed payroll webhook with 5 retries;
- HR employee and leave sync;
- LDAP sign-in tests against ldap3's in-memory mock;
- the Reports screen and the Settings › Integration additions.

## Changes Made
- **Reports — `domain/reports/`:**
  - `service.py`: one builder per type, scoped by the caller's `DataScope`, max 366 days, preview of 500 rows. The summary and chart always describe the whole result. Monthly register reuses the Phase 3 register.
  - `export.py`: Excel via XlsxWriter, times shown in each employee's timezone, minutes as h:mm, formula-neutralised text, empty cells left blank, separate summary sheet. PDF via WeasyPrint with a Jinja2 template, landscape when wide, page numbers, capped at 5,000 rows.
  - `describe.py`: filter text for headers and emails.
  - API: `GET /reports/{type}` returns 200 for a preview, or 202 `{job_id}` with `format=xlsx|pdf` (audited as `report.export`).
  - Task: `tasks/reports.export_report` runs the export with the requesting user's scope and stores the file encrypted in object storage. The job download remains owner-only. Exports are deleted after 25 h by the cleanup task.
  - `common`: `ReportType` enum; `ReportSchedule.report_type` is now validated against it.
- **Notifications — `domain/notifications/service.py` + `tasks/notifications.py`:**
  - Daily summary: HR gets the whole organisation, each manager gets their own departments.
  - Scheduled reports: daily, weekly or monthly periods; each sent once (Redis NX keys), with the Excel/PDF attached.
  - `confirm_checkin` (FR-33): sent once per employee per day, only for live events. `ProcessOutcome.checkin_text` is set when an event becomes the day's check-in.
  - `run_due_notifications` replaces the Phase 2 stub.
- **Payroll — `domain/integration/`, `api/v1/integration.py`, `tasks/integration.py`:**
  - API-client CRUD (Super Admin): the key is shown once, stored as a SHA-256 hash, and never written to the audit log.
  - `X-API-Key` auth now enforces a per-key rate limit and records `last_used_at`.
  - `GET /integration/attendance?date=` returns finalised days only.
  - Push: `push_payroll` sends days changed since the last delivery (watermark), signs with `t=…,v1=HMAC-SHA256`, retries 5 times with backoff (1–16 min), then alerts. A manual push can resend one date.
- **HR sync:** `services/hr_client.py` is a generic JSON client (array or paginated envelope, bearer token). `domain/integration/hr_sync.py`:
  - upserts employees by code;
  - deactivates only on an explicit `inactive` status (Q44);
  - matches HR leave by its HR id, removes cancelled leave in the window, and recomputes affected days.

  `create_employee` / `update_employee` accept a system actor (`None`).
- **Scheduling:** `run_due_integrations` runs every 5 min (Beat) and starts the payroll push and HR sync once per local day after their configured times.
- **LDAP:** `services/directory.py` gained `_server` / `_connect` seams so the tests can use ldap3's MOCK_SYNC directory. Sign-in behaviour is unchanged.
- **Frontend:**
  - Reports screen (`/reports`): type, date range, department, employee and status filters in the URL; summary cards, chart and preview table; Excel/PDF export that polls the job and downloads; schedule-email dialog for Admins.
  - Settings › Integration: API keys card (create with show-once dialog, enable/disable, revoke) and Run now (push to payroll with an optional date, sync from HR).
  - "Reports" added to the navigation.
  - Sign-out: the explicit navigate was removed (the route guard redirects), which fixes a double navigation seen in tests.
- **Docs:** backend README sections for reports, payroll pull/push (signature format, retries, upsert advice) and the HR JSON contract. `.env.example` comments. `open-questions.md` updated: Q28, plus new Q44–Q48.

## Files Changed
```
common/facetrack_common/{constants,settings_keys}.py
backend/app/api/v1/{reports,integration}.py, backend/app/main.py
backend/app/domain/reports/{__init__,service,export,describe}.py, backend/app/domain/reports/templates/report.html
backend/app/domain/notifications/{__init__,service}.py
backend/app/domain/integration/{__init__,api_clients,payroll,hr_sync}.py
backend/app/domain/employees/service.py, backend/app/domain/recognition/service.py
backend/app/repositories/attendance_repo.py, backend/app/schemas/{report,integration}.py
backend/app/core/security.py, backend/app/services/{hr_client,directory}.py
backend/app/worker/{celery_app,dispatch,schedule}.py, backend/app/worker/tasks/{reports,integration,notifications,events,maintenance}.py
backend/tests/conftest.py, backend/tests/domain/test_reports.py, backend/tests/api/{test_reports_api,test_integration}.py
backend/tests/worker/{test_integration_tasks,test_notifications}.py, backend/tests/services/test_hr_client.py
backend/README.md, backend/.env.example
frontend/src/pages/reports/ReportsPage.tsx, frontend/src/components/reports/*, frontend/src/components/settings/IntegrationCard.tsx
frontend/src/hooks/{useReports,useIntegration}.ts, frontend/src/lib/{reports,schemas/report}.ts
frontend/src/routes/{navigation,router}.ts(x), frontend/src/pages/settings/SettingsPage.tsx, frontend/src/components/layout/UserMenu.tsx
frontend/src/pages/__tests__/reports.test.tsx, frontend/e2e/reports-integration.spec.ts, frontend/src/api/generated/**, frontend/README.md
docs/openapi.yaml, docs/open-questions.md
```

## Database Changes
None. The payroll watermark and the "already ran today" markers are Redis keys; the existing tables cover the rest.

## Testing
- **Backend: 150 tests pass** against real PostgreSQL and Redis (38 new). Coverage 86%; ruff and mypy strict are clean.
  - Reports: every type selects the right days; department, employee and status filters; manager and employee scope; validation; preview cap with whole-result summary.
  - Excel: local times, neutralised formulas, blank cells, summary sheet. PDF renders.
  - Report API: preview, 422s, operator 403; export → 202 → task → owner-only download; export respects the employee's own scope.
  - API keys: shown once, hash-only, never in the audit log, Super Admin only. Pull: finalised days only, `last_used_at`, missing/wrong/revoked/session-cookie → 401, rate limit → 429. Manual push and sync are admin-only.
  - Push: HMAC verifies and fails when the body is tampered; each change sent once; a later correction is resent; Retry is raised, then an alert after 5 attempts; the watermark is unchanged on failure; skips when not configured.
  - HR sync: create, update, deactivate; unknown department and missing-code errors; approved leave added, pending ignored, cancelled removed; a closed Absent day becomes On leave. HR outage → alert.
  - Scheduling: once per day; schedule periods (daily, weekly on Monday, monthly on the 1st, before the configured time); daily summary to HR and to the manager; scheduled report email with PDF attached.
  - Check-in confirmation: sent once per day; no notice for replayed events.
  - HR client: pagination, token, bad responses.
  - LDAP (ldap3 mock): good password, wrong password, unknown user, filter-injection attempt, empty password.
- **Common:** 45 tests pass. **Engine:** 109 pass (+2 skipped without a test DB), checked because `common` changed.
- **Frontend:** 50 Vitest tests pass, run 3 times with no unhandled errors. New tests: report preview formatting, export job polling → download, employee history needs an employee, API key shown once. ESLint (0 warnings), `tsc` strict and `vite build` are clean.
- **End to end:** Playwright with Chromium against the real stack (API, PostgreSQL, Redis, Celery worker and beat restarted on this code):
  - report preview;
  - real **Excel and PDF downloads** produced by the Celery worker;
  - an API key created in Settings and used by an HTTP client on `/integration/attendance` (200), and a bad key (401);
  - plus the Phase 3 walk-through and tablet test.

  3 runs, 0 JavaScript errors.
- **Not verified:**
  - delivery to a real payroll system and the §16 gate (one month that matches the register exactly);
  - a real HR API (P6), real SMTP (P7) and a real Microsoft Teams webhook;
  - Active Directory itself (only ldap3's mock);
  - scheduled jobs firing on their own at clock times in a long-running deployment — the logic is tested with forced "due" times, not observed over a real day.

## Notes
- Pending owner input: P6 (HR/payroll system and field mapping, AD details) and P7 (SMTP, Teams) are unchanged. The HR/payroll contract implemented here is documented in `backend/README.md` and can be adapted in one module each (`services/hr_client.py`, `domain/integration/payroll.py`).
- Decisions: Q44 (no automatic deactivation from HR absence), Q45 (watermark push), Q46 (email-only check-in confirmation), Q47 (schedule scope), Q48 (summary audience).
- No new third-party libraries: XlsxWriter, WeasyPrint, Jinja2, httpx and ldap3 were already listed (CLAUDE.md §1.2 / Q26).
