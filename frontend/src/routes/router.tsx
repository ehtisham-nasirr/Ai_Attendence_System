import { lazy, Suspense, type ComponentType, type ReactNode } from "react";
import { createBrowserRouter, Outlet } from "react-router-dom";

import { Skeleton } from "@/components/ui/skeleton";
import { AppLayout } from "@/layouts/AppLayout";
import { AuthLayout } from "@/layouts/AuthLayout";
import { Permission, type PermissionName } from "@/lib/permissions";
import { NotFoundPage } from "@/pages/errors/NotFoundPage";
import { ForgotPasswordPage } from "@/pages/login/ForgotPasswordPage";
import { LoginPage } from "@/pages/login/LoginPage";
import { ResetPasswordPage } from "@/pages/login/ResetPasswordPage";
import { HomeRedirect, ProtectedRoute, RequireEmployee, RequirePermission } from "@/routes/guards";

function page<T extends Record<string, ComponentType>>(load: () => Promise<T>, name: keyof T) {
  return lazy(async () => ({ default: (await load())[name] }));
}

const DashboardPage = page(() => import("@/pages/dashboard/DashboardPage"), "DashboardPage");
const LiveViewPage = page(() => import("@/pages/live/LiveViewPage"), "LiveViewPage");
const EmployeesPage = page(() => import("@/pages/employees/EmployeesPage"), "EmployeesPage");
const EmployeeProfilePage = page(() => import("@/pages/employees/EmployeeProfilePage"), "EmployeeProfilePage");
const CamerasPage = page(() => import("@/pages/cameras/CamerasPage"), "CamerasPage");
const AttendancePage = page(() => import("@/pages/attendance/AttendancePage"), "AttendancePage");
const MonthlyRegisterPage = page(() => import("@/pages/register/MonthlyRegisterPage"), "MonthlyRegisterPage");
const UnknownFacesPage = page(() => import("@/pages/unknown-faces/UnknownFacesPage"), "UnknownFacesPage");
const EventLogPage = page(() => import("@/pages/events/EventLogPage"), "EventLogPage");
const CorrectionsPage = page(() => import("@/pages/corrections/CorrectionsPage"), "CorrectionsPage");
const ReportsPage = page(() => import("@/pages/reports/ReportsPage"), "ReportsPage");
const SettingsPage = page(() => import("@/pages/settings/SettingsPage"), "SettingsPage");
const AuditLogPage = page(() => import("@/pages/audit/AuditLogPage"), "AuditLogPage");
const MyAttendancePage = page(() => import("@/pages/me/MyAttendancePage"), "MyAttendancePage");

function PageFallback() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading page">
      <Skeleton className="h-8 w-56" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

function guarded(anyOf: PermissionName[], element: ReactNode) {
  return <RequirePermission anyOf={anyOf}>{element}</RequirePermission>;
}

export const routes = [
  {
    element: <AuthLayout />,
    children: [
      { path: "/login", element: <LoginPage /> },
      { path: "/forgot-password", element: <ForgotPasswordPage /> },
      { path: "/reset-password", element: <ResetPasswordPage /> },
    ],
  },
  {
    element: (
      <ProtectedRoute>
        <AppLayout />
      </ProtectedRoute>
    ),
    children: [
      {
        element: (
          <Suspense fallback={<PageFallback />}>
            <Outlet />
          </Suspense>
        ),
        children: [
          { path: "/", element: <HomeRedirect /> },
          { path: "/dashboard", element: guarded([Permission.dashboardView], <DashboardPage />) },
          { path: "/live", element: guarded([Permission.liveView], <LiveViewPage />) },
          { path: "/employees", element: guarded([Permission.employeesManage], <EmployeesPage />) },
          { path: "/employees/:employeeId", element: guarded([Permission.employeesManage], <EmployeeProfilePage />) },
          { path: "/cameras", element: guarded([Permission.camerasManage], <CamerasPage />) },
          { path: "/attendance", element: guarded([Permission.attendanceCorrect], <AttendancePage />) },
          { path: "/register", element: guarded([Permission.attendanceCorrect], <MonthlyRegisterPage />) },
          { path: "/unknown-faces", element: guarded([Permission.unknownFacesReview], <UnknownFacesPage />) },
          { path: "/events", element: guarded([Permission.eventsVoid], <EventLogPage />) },
          { path: "/corrections", element: guarded([Permission.attendanceCorrect], <CorrectionsPage />) },
          { path: "/reports", element: guarded([Permission.attendanceCorrect], <ReportsPage />) },
          {
            path: "/settings",
            element: guarded([Permission.settingsManage, Permission.usersManage], <SettingsPage />),
          },
          { path: "/audit", element: guarded([Permission.auditView], <AuditLogPage />) },
          {
            path: "/me",
            element: (
              <RequireEmployee>
                <MyAttendancePage />
              </RequireEmployee>
            ),
          },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

export function createRouter() {
  return createBrowserRouter(routes);
}
