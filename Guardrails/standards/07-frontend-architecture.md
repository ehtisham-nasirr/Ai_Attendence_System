# Frontend Architecture (React 18 + TypeScript + Vite)

The portal is a **React single-page app built with Vite**, written in **TypeScript (strict mode)**. Next.js is not used. UI components come from **shadcn/ui** on **Tailwind CSS**; icons from **lucide-react**; charts from **Recharts**.

## Layered Flow

```
Page (src/pages/*)
  ↓
Feature components (src/components/<feature>/*)
  ↓
Hooks (src/hooks/*) — TanStack Query, useLiveFeed, useAuth
  ↓
Generated API client (src/api/generated/*)
  ↓
FastAPI REST API (/api/v1) and WebSocket (/ws/live)
```

Do not call the API directly from components — see `standards/08-frontend-state-and-api-layer.md`.

## Source Layout

```
src/
├── api/            generated client (do not edit) + axios instance with interceptors
├── components/
│   ├── ui/         shadcn/ui primitives (Button, Dialog, Table, Badge ...)
│   ├── common/     app-wide pieces: DataTable, PageHeader, EmptyState, StatusBadge, ConfirmDialog
│   └── <feature>/  employees/, cameras/, attendance/, corrections/, unknown-faces/, reports/, settings/
├── hooks/
├── layouts/        AppLayout (sidebar + top bar with location switcher), AuthLayout
├── pages/          one folder per screen in requirements §13
├── routes/         router config, ProtectedRoute, role guards
├── lib/            utils, date/time formatting (UTC → Asia/Karachi), zod schemas
└── types/
```

## Component Standards

Each component should have **one clear responsibility**.

**Bad — a single component doing everything:**

```
DashboardPage.tsx
- API calls and WebSocket handling
- permission logic
- attendance status calculations
- 1000 lines of UI
- form validation
```

**Prefer — composed, focused components:**

```
DashboardPage
├── KpiCards
├── HourlyArrivalsChart
├── DepartmentAttendanceChart
├── LiveEventFeed
└── CameraHealthStrip
```

- Extract a reusable component once the same UI pattern appears **more than once**. All list screens use the shared `DataTable` (TanStack Table) with search, filters, sort and export — do not build a new table per page.
- Do not create abstractions for one-time code without a clear benefit.
- **Never compute business results in the frontend** (attendance status, late minutes, worked hours, recognition decisions). Display what the API returns.
- Status is always shown with colour **and** text (`StatusBadge`), never colour alone (requirements §13).
- Every list/page handles loading (skeletons, not spinners), empty states with a next action, and errors.
- Every destructive action uses `ConfirmDialog`; biometric erasure requires typing the employee code.
- Support light and dark themes through Tailwind/shadcn theme tokens — no hardcoded colours.

## Naming Conventions

| Kind | Convention | Example |
|---|---|---|
| Components | `PascalCase.tsx` | `EmployeeTable.tsx`, `CameraForm.tsx`, `LiveEventFeed.tsx` |
| Pages | `PascalCasePage.tsx` | `AttendancePage.tsx`, `UnknownFacesPage.tsx` |
| Hooks | `useX.ts` | `useEmployees.ts`, `useLiveFeed.ts`, `useAuth.ts` |
| Zod schemas | `xSchema` in `lib/schemas/` | `shiftSchema`, `cameraSchema` |
| Functions | `camelCase`, verb-first | `formatWorkedHours()`, `toLocalTime()` |
| Variables | `camelCase` | `const employeeList = []`, `const isLoading = false` |
| Types / interfaces | `PascalCase` | `type CameraMode = "IDLE" \| "ACTIVE" ...` |

## TypeScript Rules

- `strict: true`; no `any` (use `unknown` and narrow). Types for API data come from the generated client — do not redeclare them by hand.
- No `// @ts-ignore` without a comment explaining why.
