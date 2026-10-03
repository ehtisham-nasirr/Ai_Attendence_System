import { z } from "zod";

export function splitRecipients(text: string): string[] {
  return text
    .split(/[,;\s]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

export const reportScheduleSchema = z.object({
  report_type: z.enum([
    "daily",
    "monthly_register",
    "late_arrivals",
    "early_exits",
    "absentee",
    "overtime",
    "department_summary",
  ]),
  frequency: z.enum(["daily", "weekly", "monthly"]),
  time: z.string().regex(/^\d{2}:\d{2}$/, "Enter a time"),
  recipients: z
    .string()
    .refine((text) => splitRecipients(text).length > 0, "Add at least one recipient")
    .refine((text) => splitRecipients(text).length <= 50, "At most 50 recipients")
    .refine(
      (text) => splitRecipients(text).every((address) => z.email().safeParse(address).success),
      "One of the addresses is not valid",
    ),
  department_id: z.string(),
  format: z.enum(["xlsx", "pdf"]),
});

export type ReportScheduleValues = z.infer<typeof reportScheduleSchema>;

/** As stored in the setting `notifications.report_schedules`. */
export interface StoredSchedule {
  report_type: string;
  frequency: "daily" | "weekly" | "monthly";
  time: string;
  recipients: string[];
  department_id: number | null;
  format: "xlsx" | "pdf";
}
