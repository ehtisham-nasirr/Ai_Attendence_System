import type { AttendanceStatus, CorrectionField } from "@/api/generated/model";
import { formatDateTime } from "@/lib/format";
import { attendanceStatusLabel } from "@/lib/labels";

/** Shows a correction's old/new value: a time in the display timezone, or a status label. */
export function formatCorrectionValue(field: CorrectionField, value: string | null, timeZone: string): string {
  if (value === null || value === "") return "—";
  if (field === "status") return attendanceStatusLabel[value as AttendanceStatus]?.label ?? value;
  return formatDateTime(value, timeZone);
}
