/** Human labels and badge tones for API enums. Status is always shown as colour + text (§13). */
import type {
  AttendanceStatus,
  CameraMode,
  CameraRole,
  CameraStatus,
  CorrectionField,
  CorrectionStatus,
  EmployeeStatus,
  RecognitionStatus,
  ReviewStatus,
  UserRole,
} from "@/api/generated/model";

export type Tone = "ok" | "warn" | "bad" | "info" | "neutral" | "leave";

export const attendanceStatusLabel: Record<AttendanceStatus, { label: string; tone: Tone }> = {
  present: { label: "Present", tone: "ok" },
  late: { label: "Late", tone: "warn" },
  early_exit: { label: "Early exit", tone: "warn" },
  half_day: { label: "Half day", tone: "warn" },
  absent: { label: "Absent", tone: "bad" },
  on_leave: { label: "On leave", tone: "leave" },
  holiday: { label: "Holiday", tone: "neutral" },
  weekly_off: { label: "Weekly off", tone: "neutral" },
  missing_checkout: { label: "Missing check-out", tone: "bad" },
};

/** Register letters (§13 screen 8, Q31) and what they stand for, for the legend. */
export const statusLetterLegend: { letter: string; label: string; tone: Tone }[] = [
  { letter: "P", label: "Present", tone: "ok" },
  { letter: "L", label: "Late", tone: "warn" },
  { letter: "EE", label: "Early exit", tone: "warn" },
  { letter: "HD", label: "Half day", tone: "warn" },
  { letter: "A", label: "Absent", tone: "bad" },
  { letter: "MC", label: "Missing check-out", tone: "bad" },
  { letter: "LV", label: "On leave", tone: "leave" },
  { letter: "H", label: "Holiday", tone: "neutral" },
  { letter: "WO", label: "Weekly off", tone: "neutral" },
];

export const cameraStatusLabel: Record<CameraStatus, { label: string; tone: Tone }> = {
  online: { label: "Online", tone: "ok" },
  offline: { label: "Offline", tone: "bad" },
  disabled: { label: "Disabled", tone: "neutral" },
  unknown: { label: "Unknown", tone: "neutral" },
};

export const cameraModeLabel: Record<CameraMode, { label: string; tone: Tone }> = {
  ACTIVE: { label: "Active", tone: "ok" },
  COOLDOWN: { label: "Cooldown", tone: "info" },
  IDLE: { label: "Idle", tone: "neutral" },
  PAUSED: { label: "Paused", tone: "warn" },
};

export const cameraRoleLabel: Record<CameraRole, string> = {
  ENTRY: "Entry",
  EXIT: "Exit",
  ENTRY_EXIT: "Entry + exit",
  GENERAL: "General",
};

export const recognitionStatusLabel: Record<RecognitionStatus, { label: string; tone: Tone }> = {
  recognized: { label: "Recognised", tone: "ok" },
  unknown: { label: "Unknown", tone: "warn" },
  voided: { label: "Voided", tone: "neutral" },
};

export const reviewStatusLabel: Record<ReviewStatus, { label: string; tone: Tone }> = {
  pending: { label: "Pending", tone: "warn" },
  assigned: { label: "Assigned", tone: "ok" },
  dismissed: { label: "Dismissed", tone: "neutral" },
};

export const correctionStatusLabel: Record<CorrectionStatus, { label: string; tone: Tone }> = {
  pending: { label: "Pending", tone: "warn" },
  approved: { label: "Approved", tone: "ok" },
  rejected: { label: "Rejected", tone: "bad" },
};

export const correctionFieldLabel: Record<CorrectionField, string> = {
  check_in_at: "Check-in",
  check_out_at: "Check-out",
  status: "Status",
};

export const employeeStatusLabel: Record<EmployeeStatus, { label: string; tone: Tone }> = {
  active: { label: "Active", tone: "ok" },
  inactive: { label: "Inactive", tone: "neutral" },
};

export const roleLabel: Record<UserRole, string> = {
  super_admin: "Super Admin",
  hr_admin: "HR Admin",
  department_manager: "Department Manager",
  operator: "Security / IT Operator",
  employee: "Employee",
};
