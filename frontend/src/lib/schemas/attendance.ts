import { z } from "zod";

const reason = z.string().trim().min(5, "Give a reason (at least 5 characters)").max(1000);

export const correctionSchema = z
  .object({
    field: z.enum(["check_in_at", "check_out_at", "status"]),
    date: z.string(),
    time: z.string(),
    status: z.string(),
    reason,
  })
  .superRefine((values, ctx) => {
    if (values.field === "status") {
      if (!values.status) ctx.addIssue({ code: "custom", path: ["status"], message: "Choose the correct status" });
    } else {
      if (!values.date) ctx.addIssue({ code: "custom", path: ["date"], message: "Choose the date" });
      if (!values.time) ctx.addIssue({ code: "custom", path: ["time"], message: "Enter the time" });
    }
  });
export type CorrectionFormValues = z.infer<typeof correctionSchema>;

export const manualEntrySchema = z
  .object({
    employee_id: z.number({ error: "Choose an employee" }).int().positive("Choose an employee"),
    work_date: z.string().min(1, "Choose the date"),
    check_in: z.string(),
    check_out: z.string(),
    check_out_next_day: z.boolean(),
    status: z.string(),
    reason,
  })
  // "auto" means "calculate from the times", so it does not count as a value on its own.
  .refine((v) => v.check_in || v.check_out || (v.status !== "" && v.status !== "auto"), {
    path: ["check_in"],
    message: "Enter a check-in, a check-out or a status",
  });
export type ManualEntryValues = z.infer<typeof manualEntrySchema>;

export const reasonSchema = z.object({ reason: z.string().trim().min(3, "Give a reason").max(500) });
export type ReasonValues = z.infer<typeof reasonSchema>;

export const decisionSchema = z.object({ comment: z.string().trim().max(1000) });
export type DecisionValues = z.infer<typeof decisionSchema>;
