import {
  CalendarDays,
  Camera,
  ClipboardCheck,
  ClipboardList,
  FileText,
  LayoutDashboard,
  ListChecks,
  ScanFace,
  Settings,
  ShieldCheck,
  UserRound,
  Users,
  Video,
  type LucideIcon,
} from "lucide-react";

import { Permission, type PermissionName } from "@/lib/permissions";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Shown when the user has any of these permissions (requirements §13 role column). */
  anyOf: PermissionName[];
  /** Only for employee accounts (self-service). */
  employeeOnly?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, anyOf: [Permission.dashboardView] },
  { to: "/live", label: "Live view", icon: Video, anyOf: [Permission.liveView] },
  { to: "/employees", label: "Employees", icon: Users, anyOf: [Permission.employeesManage] },
  { to: "/cameras", label: "Cameras", icon: Camera, anyOf: [Permission.camerasManage] },
  { to: "/attendance", label: "Attendance", icon: ClipboardCheck, anyOf: [Permission.attendanceCorrect] },
  { to: "/register", label: "Monthly register", icon: CalendarDays, anyOf: [Permission.attendanceCorrect] },
  { to: "/unknown-faces", label: "Unknown faces", icon: ScanFace, anyOf: [Permission.unknownFacesReview] },
  { to: "/events", label: "Event log", icon: ListChecks, anyOf: [Permission.eventsVoid] },
  { to: "/corrections", label: "Corrections", icon: ClipboardList, anyOf: [Permission.attendanceCorrect] },
  { to: "/reports", label: "Reports", icon: FileText, anyOf: [Permission.attendanceCorrect] },
  { to: "/settings", label: "Settings", icon: Settings, anyOf: [Permission.settingsManage, Permission.usersManage] },
  { to: "/audit", label: "Audit log", icon: ShieldCheck, anyOf: [Permission.auditView] },
  { to: "/me", label: "My attendance", icon: UserRound, anyOf: [Permission.correctionsRequest], employeeOnly: true },
];

export function visibleNavItems(can: (p: PermissionName) => boolean, isEmployee: boolean): NavItem[] {
  return NAV_ITEMS.filter((item) => (item.employeeOnly ? isEmployee : item.anyOf.some(can)));
}
