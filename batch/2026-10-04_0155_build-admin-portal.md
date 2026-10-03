# Batch: build-admin-portal

**Date:** 2026-10-04 01:55
**Type:** feature
**Command Used:** commands/new-feature.md
**Standards Referenced:** standards/01, 04, 07, 08, 09, 11, 12, 13, 15, 16, 18
**Requirements:** §13 screens 1–11, 13, 14; FR-2, FR-3, FR-5, FR-6, FR-7, FR-8, FR-9, FR-10, FR-11, FR-13, FR-21, FR-22, FR-24, FR-25, FR-26, FR-27, FR-28, FR-29, FR-36, FR-37, FR-38, FR-40; NFR-14

## Summary
Built the admin portal (requirements §16, Phase 4 "Admin portal UI"): React 18 + TypeScript strict + Vite, shadcn/ui on Tailwind 4, TanStack Query/Table, React Hook Form + Zod, Recharts, and an orval client generated from `docs/openapi.yaml`.
- 13 of the 14 §13 screens are done. **Reports (screen 12) is deferred to the Phase 4 batch**, together with its backend endpoints.
- Small, additive backend changes the screens needed: monthly register endpoint, public sign-in options, display timezone on the profile.
- A real backend gap was fixed: adding or removing leave, or changing a holiday, did not recompute attendance days that already existed.

## Changes Made
- **Frontend foundation:**
  - **API layer:** `src/api/client.ts` is the single axios instance (session cookie, CSRF header, envelope error normalising, 401 handling). `src/api/generated/` holds the orval output: 73 functions and typed models.
  - **Session and live data:**
    - `AuthProvider` handles the profile, permissions, display timezone and sign-out.
    - `LiveFeedProvider` is the one `/ws/live` socket: backoff reconnect, pause while hidden, no reconnect after 4401. Messages update or invalidate the query cache, with throttled refetches.
  - **Hooks:** one per resource; filters and paging live in the URL.
  - **Shared components:** `DataTable` (server paging and sort, skeletons, empty and error states, CSV export of the current filter), `StatusBadge` (colour + text), `ConfirmDialog` (type-the-code for biometric erasure), `EmptyState`, `ErrorState`, `SearchInput`, `FilterSelect`, `EmployeeCombobox`, `SecureImage`.
  - **Layout:** sidebar and top bar with location switcher, notifications (pending corrections and unknown faces), live status, theme switch and user menu. Light and dark themes. The sidebar becomes a drawer below 1024 px (tablet).
- **Screens:**
  - Login, forgot password and reset password; AD button shown only when enabled.
  - Dashboard: KPIs, hourly and department charts, live event feed with snapshots, camera strip with load level.
  - Live view: WHEP/WebRTC tiles at 1/4/9/16, recognition boxes from `/ws/live`, click to expand.
  - Employees: search and filters, bulk import with job progress and error list.
  - Employee profile:
    - details and consent date;
    - face gallery with quality score and delete;
    - enroll by drag-and-drop or webcam (face-guide oval, live brightness and sharpness hints), with per-photo results and duplicate warnings;
    - attendance calendar and leave;
    - erase biometrics and delete employee (type the code to confirm).
  - Cameras: card or table view; add/edit drawer with encrypted, write-only stream URLs, connection test and snapshot, ROI polygon editor, FPS and threshold sliders, operating hours.
  - Attendance: daily table with snapshot on hover, correction dialog (apply or request, by role), manual entry.
  - Monthly register; Unknown faces (similarity groups, assign or dismiss); Event log (void with reason); Corrections (tabs, old vs new, decide with comment).
  - Settings: an editor generated from the settings registry (asks for confirmation when recognition is made less strict), plus organisation, shifts, holidays, and users and roles.
  - Audit log with before/after values; My attendance (calendar, month totals, own requests).
- **React 18 compatibility (Q39):** shadcn/ui now targets React 19, where `ref` is a prop. The UI components are wrapped with `fwd()` (`src/lib/forwardRef.ts`). Without it, refs to `asChild` triggers, Radix presence and form inputs were silently dropped; this was found through a test warning.
- **Backend additions:**
  - `GET /api/v1/attendance/register` (`domain/attendance/register.py`, scope-filtered).
  - `GET /api/v1/auth/options`; `timezone` on `/auth/me` and the login response.
  - `domain/leaves/service.py` recomputes existing days on leave create and delete.
  - Holiday create/update/delete dispatch `recompute_date` (`worker/dispatch.recompute_attendance_date`).
  - Operation IDs are already route names (Phase 2).
- **Tooling:**
  - `frontend/Dockerfile` (static build → Nginx :8080) and `nginx-spa.conf`; root `.dockerignore`.
  - Makefile targets `test-frontend`, `lint-frontend`, `build-frontend`, `e2e`; `gen-api` now also regenerates the client.
  - Playwright config and `e2e/portal.spec.ts`.

## Files Changed
```
frontend/{package.json,package-lock.json,index.html,vite.config.ts,tsconfig*.json,eslint.config.js,components.json,orval.config.ts,playwright.config.ts,Dockerfile,nginx-spa.conf,.env.example,README.md}
frontend/public/favicon.svg
frontend/src/{main.tsx,App.tsx,index.css,vite-env.d.ts}
frontend/src/api/{client.ts,media.ts,generated/**}
frontend/src/components/{ui,common,layout,dashboard,employees,cameras,live,attendance,corrections,unknown-faces,events,settings}/**
frontend/src/hooks/*.ts, frontend/src/layouts/*.tsx, frontend/src/routes/*.ts(x), frontend/src/pages/**
frontend/src/lib/{utils,format,labels,permissions,live,csv,query,forms,month,whep,imageQuality,settingsMeta,correctionValue,forwardRef}.ts, lib/schemas/*.ts
frontend/src/test/*, frontend/src/**/__tests__/*, frontend/e2e/portal.spec.ts
backend/app/api/v1/{attendance,auth}.py, backend/app/domain/attendance/register.py, backend/app/domain/auth/service.py
backend/app/domain/leaves/service.py, backend/app/domain/organization/service.py, backend/app/worker/dispatch.py
backend/app/repositories/attendance_repo.py, backend/app/schemas/{attendance,auth}.py, backend/README.md
backend/tests/api/{test_register_and_profile,test_leave_holiday_recompute}.py
docs/openapi.yaml, docs/open-questions.md (P11, Q36–Q43), Makefile, .dockerignore
```

## Database Changes
None (no migration). The new endpoints read existing tables.

## Testing
- **Frontend unit/component — 46 tests, 9 files (Vitest + RTL + MSW):**
  - Live message handling: dedupe, cap, overlay TTL, invalidations, throttling.
  - `LiveFeedProvider`: cache writes, backoff reconnect, no reconnect on 4401, close on unmount.
  - Timezone conversions; CSV quoting and formula neutralising.
  - Settings editor: changed-keys-only payload, confirmation when lowering strictness, per-key API errors.
  - DataTable: loading, rows, paging, sort cycle, empty and error states.
  - ConfirmDialog type-to-confirm.
  - Sign-in: success with return path, error message, validation focus (proves refs work), AD button.
  - Route guards and role menus; session expiry; sign-out regression test.
  - Employees list: data, search, empty, error.
  - Correction flow: HR applies local time → UTC payload; employee sends a request; API field error shown.
  - Corrections approve with comment; dashboard KPIs.
- **Checks:** ESLint (0 warnings), `tsc -b` strict, and `vite build` are clean.
- **Coverage:** 29% of statements overall. Libraries 72%; several page components have no unit tests and are covered only by the E2E run below.
- **End to end, verified:** Playwright with Chromium against the real dev stack (FastAPI :8000, PostgreSQL `facetrack_dev`, Redis, Celery worker, engine :8100 with a synthetic camera), serving the production build through `vite preview` with the same `/api` and `/ws` proxying as Nginx. As Super Admin it:
  - creates a location, department and shift;
  - visits all settings tabs;
  - creates an employee and checks every profile tab;
  - adds leave and a manual attendance entry;
  - applies a status correction and sees it under approved corrections;
  - checks the register row;
  - loads live view, cameras, unknown faces, event log and audit log (filtered to `employee.create`);
  - signs out.

  There were 0 JavaScript errors. The tablet (820 px) drawer navigation test also passed. Screenshots were reviewed (dashboard, attendance, register, cameras, settings, enrollment).
- **Bugs found by these tests and fixed:**
  - sign-out returned to the dashboard (the query cache was cleared under a live observer);
  - refs were dropped under React 18;
  - setState-in-effect patterns;
  - a stream arriving during the live tile's error state was lost.
- **Backend:** 112 tests pass (6 new: register letters, totals and scope; profile timezone; auth options; leave turns a closed Absent day into On leave and back; holiday changes queue recompute; `recompute_date` applies a new holiday). Coverage 83%; ruff and mypy clean.
- **Not verified:**
  - live video (no MediaMTX or real camera here; tiles show "Live view unavailable" and retry);
  - webcam capture (no camera device in headless Chromium);
  - photo enrollment end to end (no consented face photos);
  - Active Directory sign-in;
  - the HR usability session (§16 Phase 4 gate);
  - the frontend Docker image build (Phase 5).

## Notes
- Decisions recorded in `docs/open-questions.md`: P11 (logo file), Q36 (per-node load instead of per-camera CPU), Q37 (`VITE_API_ORIGIN`), Q38 (envelope kept for pagination), Q39 (React 18 + shadcn forwardRef), Q40 (new additive endpoints), Q41 (recompute on leave/holiday change), Q42 (list CSV vs Celery report exports), Q43 (group assignment).
- Libraries added: shadcn/ui's own dependencies (`radix-ui`, `cmdk`, `class-variance-authority`, `clsx`, `tailwind-merge`, `tw-animate-css`), `sonner`, `axios`, `@playwright/test` (pinned to the pre-installed Chromium revision).
- Outside the listed layout (flagged per §0.4): `frontend/e2e/` (Playwright, standards/11) and `src/test/` (test helpers).
