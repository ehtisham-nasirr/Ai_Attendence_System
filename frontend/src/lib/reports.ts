import type { AttendanceStatus, ReportType } from "@/api/generated/model";

export const REPORTS: { type: ReportType; label: string; description: string; statusFilter: boolean }[] = [
  { type: "daily", label: "Daily attendance", description: "Every employee-day with times, minutes and status.", statusFilter: true },
  { type: "monthly_register", label: "Monthly register", description: "Status letter per employee per day, with totals (month of the start date).", statusFilter: false },
  { type: "late_arrivals", label: "Late arrivals", description: "Days with late minutes after the grace period.", statusFilter: false },
  { type: "early_exits", label: "Early exits", description: "Days that ended before the shift end minus grace.", statusFilter: false },
  { type: "absentee", label: "Absentee", description: "Days marked Absent at day close.", statusFilter: false },
  { type: "overtime", label: "Overtime", description: "Days with overtime beyond the threshold.", statusFilter: false },
  { type: "department_summary", label: "Department summary", description: "Attendance totals per department.", statusFilter: true },
  { type: "employee_history", label: "Employee history", description: "All days of one employee.", statusFilter: true },
];

export function reportInfo(type: ReportType) {
  return REPORTS.find((report) => report.type === type) ?? REPORTS[0];
}

/** File name the backend gives exports (kept in sync with worker/tasks/reports.file_name). */
export function exportFileName(type: ReportType, dateFrom: string, dateTo: string, format: "xlsx" | "pdf"): string {
  return `facetrack-${type}-${dateFrom.replaceAll("-", "")}-${dateTo.replaceAll("-", "")}.${format}`;
}

export function isStatus(value: unknown): value is AttendanceStatus {
  return typeof value === "string";
}
