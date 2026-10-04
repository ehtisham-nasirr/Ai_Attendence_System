# Batch: light-cream-theme-and-fonts

**Date:** 2026-10-04 16:32
**Type:** feature
**Command Used:** commands/new-feature.md (scaled to a frontend-only presentation change)
**Standards Referenced:** standards/07-frontend-architecture.md, standards/08-frontend-state-and-api-layer.md, standards/11-testing.md, standards/13-documentation-and-comments.md
**Requirements:** §13 (UI/UX: light and dark themes, one accent colour, status as colour plus text, responsive to tablet)

## Summary
The owner found the portal too dark and "vibe-coded". The theme followed the operating system, so on a Windows laptop in dark mode it was dark navy with neon blue/green. The portal now opens in a calm light theme for every user: warm white/cream surfaces, warm-grey borders, near-black warm text, one deep corporate-blue accent and the system UI font (Segoe UI on Windows). Dark and System are still in the user menu, and every screen and feature works as before.

## Changes Made
- **Default theme:** `ThemeProvider` now defaults to `light` instead of `system`, and stores the choice under a new key, `facetrack.theme.v2`. Browsers that already had `system` saved under the old `facetrack.theme` key therefore start on light. The old key is removed. Unknown stored values fall back to light. The Light/Dark/System radio in the user menu is unchanged.
- **Light tokens (`:root` in `src/index.css`):** a new palette. Cream page `#faf7f1`, white cards and popovers, a deeper cream sidebar `#f4eee5`, warm-grey borders, text `#28211c`, and a single primary `#1c4c8a` (deep corporate blue). Muted text is `#6a615a`. Status colours (ok/warn/bad/info/neutral/leave) are darkened so that their text is at least 4.5:1 on white, on cream and on their own badge tint. Chart colours were chosen to read on white. Radius is 0.5rem. `color-scheme` is now set (light, and dark under `.dark`), so native controls such as date pickers and scrollbars match the theme.
- **Sidebar tokens** (`--sidebar-primary`, `--sidebar-accent`, `--sidebar-accent-foreground`, `--sidebar-border`) added to both themes. The active nav item is now a white pill with blue text and a blue left bar, and inactive items use dark warm-grey text instead of muted text. The mobile drawer uses the sidebar colours too.
- **Dark theme:** all existing dark tokens are unchanged. Dark never had its own `--chart-*` values (it inherited the light ones), so the previous bright chart colours are now pinned in `.dark` and dark charts look exactly as before.
- **Type:** `--font-sans` is `"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif`. No web fonts and no npm packages were added. Body text is 15px with line-height 1.5. `text-xs` is raised from 12px to 13px for all secondary text. Headings drop `tracking-tight`. Card titles are 16px semibold, table headers semibold on a cream header band, and table rows have more vertical padding (`py-2.5`). The horizontal cell padding stays at `px-2`, as before. KPI labels are medium weight and report summary labels are `text-sm`. Employee and department codes use the UI font with tabular figures instead of monospace. The code lines in the Employees code column and under the name on Attendance and Monthly register stay at 12px, as before, so the tables do not get wider; technical strings (API keys, audit actions, typed confirmations) stay monospace.
- **Removed the "AI look":** the top bar is solid white with a border instead of translucent with a backdrop blur. Cards, outline buttons, inputs, selects and textareas sit on white with `shadow-xs`. Dialogs and sheets use the popover surface. Active tabs are white, and inactive tab text uses `text-muted-foreground` (5.28:1) instead of `text-foreground/60` (about 4.2:1). StatusBadge uses a uniform 10% tint with a 25% ring.
- **Toasts:** Sonner `richColors` now take their success/info/warning/error colours from the status tokens instead of Sonner's built-in palette, so toasts follow the theme.
- **Layout defects found in the screenshots and fixed:**
  - In the Live events card, the status badge was clipped: Radix ScrollArea's `display: table` wrapper stopped `truncate` from working.
  - On tablet, the Settings tab strip wrapped outside its background. The employee profile tab strip had the same latent issue.
  - The Reports filter card, the Settings group cards and the employee details card had double top padding.
  - In two-column forms, right-hand fields sat lower than their neighbours (Add employee: Location, Status). `FormItem` now uses `content-start`.
  - The register's sticky "Employee" header cell did not match the header band.
  - The camera drawer's sticky footer used the page colour inside the white drawer.
  - The Enroll drop zone border was faint. It is now white with the input-border colour.
- **Fixes after the independent review:**
  - Attendance calendar (employee profile "Attendance history" and "My attendance"): a day with status, check-in/out and worked time no longer fits the fixed `h-20` cell at the new 13px `text-xs`, so the bottom of letters was cut off ("Half day" read "Half dav"). The cell is now `min-h-20` and grows to fit.
  - Tables: the wider `px-3` cell padding pushed the Attendance "Correct" column behind a horizontal scroll at a 1280px window. `TableHead`/`TableCell` are back to `px-2`, and the code lines listed above stay at 12px.
- Tests: new `ThemeProvider.test.tsx` with 6 cases: light by default with OS dark mode, the legacy `system` key ignored and removed, a stored dark choice kept, System following the OS, an unknown value falling back to light, and the user menu still offering Light/Dark/System with Dark applying at once.
- `frontend/README.md`: theme and font behaviour documented.

## Files Changed
```
frontend/README.md
frontend/src/index.css
frontend/src/hooks/useTheme.ts
frontend/src/layouts/AppLayout.tsx
frontend/src/components/common/ThemeProvider.tsx
frontend/src/components/common/__tests__/ThemeProvider.test.tsx (new)
frontend/src/components/common/DataTable.tsx
frontend/src/components/common/PageHeader.tsx
frontend/src/components/common/StatusBadge.tsx
frontend/src/components/layout/SidebarNav.tsx
frontend/src/components/dashboard/KpiCards.tsx
frontend/src/components/dashboard/HourlyArrivalsChart.tsx
frontend/src/components/dashboard/DepartmentAttendanceChart.tsx
frontend/src/components/dashboard/LiveEventFeed.tsx
frontend/src/components/reports/ReportOverview.tsx
frontend/src/components/reports/ReportTable.tsx
frontend/src/components/settings/OrganizationTab.tsx
frontend/src/components/employees/EnrollPanel.tsx
frontend/src/components/cameras/CameraForm.tsx
frontend/src/components/attendance/AttendanceCalendar.tsx
frontend/src/components/ui/{alert-dialog,button,card,dialog,form,input,select,sheet,sonner,table,tabs,textarea}.tsx
frontend/src/pages/attendance/AttendancePage.tsx
frontend/src/pages/employees/EmployeesPage.tsx
frontend/src/pages/employees/EmployeeProfilePage.tsx
frontend/src/pages/events/EventLogPage.tsx
frontend/src/pages/register/MonthlyRegisterPage.tsx
frontend/src/pages/reports/ReportsPage.tsx
frontend/src/pages/settings/SettingsPage.tsx
```

## Database Changes
None.

## CPU / Performance Impact
N/A (frontend styling only). Measured build sizes: main JS 718,230 → 719,380 bytes (+1.1 kB, the Sonner token map and theme-key handling); main CSS 77,813 → 77,653 bytes.

## Testing
- `npm run lint`, `npm run typecheck`, `npm test` (11 files, 56 tests, including the 6 new theme tests) and `npm run build` all pass.
- WCAG contrast was computed with a small script: the light tokens are parsed from `index.css` and converted oklch → OKLab → sRGB, and badge tints are blended the way the browser draws them. All 67 checks pass:
  - foreground: 14.79:1 on cream, 15.81:1 on white
  - muted text: 5.63:1 on cream, 6.02:1 on white, 5.28:1 on muted, 5.23:1 on the sidebar
  - sidebar text: 10.25:1; active item text 10.10:1; primary button text 8.17:1; links 8.53:1 on white and 7.98:1 on cream; destructive 6.08:1
  - status text on white: ok 6.18, warn 6.22, bad 6.08, info 6.00, neutral 6.02, leave 6.46
  - status text on its own 10% badge, over white / over cream: ok 5.35/5.02, warn 5.38/5.05, bad 5.16/4.85, info 5.19/4.87, neutral 5.25/4.93, leave 5.58/5.24
  - toast text on its tint: 5.19 to 5.56
  - chart fills on white: 7.50, 4.60, 3.19, 5.22, 5.79 (non-text minimum 3:1)
  - focus ring: 6.04:1
  - Not held to 3:1, by design (subtle borders): input border 1.63:1 and divider 1.33:1 against white.
- Visual check: dev backend (uvicorn on :8000 against `facetrack_dev`) and the built portal (`vite preview` on :4173). A Playwright script signed in as the dev Super Admin with the browser set to OS dark mode, at 1440×900 and 820×1180. It confirmed the `<html>` class is empty (light), the body font is the new stack and the size is 15px, and it captured login, dashboard, employees, employee Enroll tab, attendance, monthly register, reports (empty and after Run report), settings → organization, user menu, an export toast, the Add employee drawer, and dashboard/employees after switching to Dark. Every screenshot was reviewed and the defects listed above were fixed and re-shot.
- The existing e2e suite (`npx playwright test`, 3 tests, desktop + tablet) passes. The first run failed only on the report Excel/PDF download because no Celery worker was running. With a dev worker started, all 3 tests pass, including the full "every screen" walk that creates an employee through the Add employee form.
- Review-fix re-check (after the fixes above): `npm run lint`, `npm run typecheck`, `npm test` (11 files, 56 tests), `npm run build` and the e2e suite (3/3, with a dev Celery worker) pass again. The fixed build and the pre-change build were compared side by side in Chromium, with `Segoe UI` mapped to Liberation Sans through a scratch fontconfig file so that both builds draw the same font, as both would use Segoe UI on Windows:
  - Calendar day cell with Half day, 09:00–13:15 and 4h 15m: every line now shows in full (clientHeight equals scrollHeight: 18/18, 17/17, 17/17). The cell is 89px tall instead of 80px. The pre-change build measured 14/16 on the status line.
  - At 1280px, the Attendance table is 990px of content in a 990px container, so nothing is hidden and "Correct" shows in full, the same as before the change. It was 1066px with `px-3`. Employees also fits (990/990).
  - At 820px (tablet), both tables already scrolled sideways before this change. Employees is now 852px against 834px before, and Attendance 983px against 952px before, so one more column (Enrollment, Late / early) starts behind the scroll. The rest comes from the bold header weight (Liberation Sans has no semibold and draws it bold) and proportional codes. Left as is (minor, see Notes).
- Not tested: a real Windows machine. The sandbox has no Segoe UI, so the screenshots render in DejaVu Sans, which is wider than Segoe UI; they are a worst case for text width. Not tested in Firefox or Safari.

## Notes
- PostgreSQL and Redis on the host were down at the start, so they were started with `service ... start` (dev services) and left running. The backend, Celery worker and preview servers started for testing were stopped.
- Raw colours left on purpose: the black video backgrounds and white overlay text in Live view and Webcam capture (video surfaces), the `bg-black/50` modal scrims, the slider thumb and the white count on the red notification dot (6.08:1).
- The monthly register still scrolls horizontally at 1440px for a 31-day month, as it did before. The register's sticky first column stays white when its row is hovered (minor, unchanged).
- Live events card at 1280px: the second line ("camera · time · confidence") can now end in "…". This follows from the fix that stops the status badge being cut off, plus the 13px `text-xs`. The full text is still on the Event log page. Not changed.
- Tablet (820px): Employees and Attendance tables scroll sideways as before, and one more column now starts behind the scroll (see Testing). On Windows, Segoe UI has a real semibold face that is narrower than the bold that the sandbox draws, so the real difference should be smaller. Not verified on Windows.
- The owner's separate "error when adding an employee" report is not part of this change. In this sandbox, adding an employee through the UI works in the e2e walk against the dev backend.
