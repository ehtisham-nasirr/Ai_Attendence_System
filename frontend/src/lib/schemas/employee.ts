import { z } from "zod";

const optionalText = (max: number) => z.string().trim().max(max, `At most ${max} characters`);

export const employeeSchema = z.object({
  employee_code: z
    .string()
    .trim()
    .min(1, "Employee code is required")
    .max(64)
    .regex(/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/, "Letters, digits, dot, dash or underscore"),
  full_name: z.string().trim().min(1, "Name is required").max(200),
  department_id: z.string(),
  designation: optionalText(120),
  shift_id: z.string(),
  location_id: z.string(),
  email: z.union([z.literal(""), z.email("Enter a valid email address")]),
  phone: optionalText(32),
  status: z.enum(["active", "inactive"]),
  /** Date the signed consent form was received (standards/18); empty = no consent yet. */
  consent_date: z.string(),
  hr_external_id: optionalText(64),
});

export type EmployeeFormValues = z.infer<typeof employeeSchema>;

export const leaveSchema = z
  .object({
    from_date: z.string().min(1, "Choose the first day"),
    to_date: z.string().min(1, "Choose the last day"),
    type: z.string().trim().min(1, "Enter the leave type").max(64),
  })
  .refine((v) => v.to_date >= v.from_date, { path: ["to_date"], message: "Must be on or after the first day" });

export type LeaveFormValues = z.infer<typeof leaveSchema>;
