import { z } from "zod";

export const locationSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(120),
  address: z.string().trim().max(500),
  timezone: z.string().min(1),
});
export type LocationValues = z.infer<typeof locationSchema>;

export const departmentSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(120),
  code: z
    .string()
    .trim()
    .min(1, "Code is required")
    .max(32)
    .regex(/^[A-Za-z0-9_-]+$/, "Letters, digits, dash or underscore"),
  manager_user_id: z.string(),
});
export type DepartmentValues = z.infer<typeof departmentSchema>;

export const shiftSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(120),
  start_time: z.string().regex(/^\d{2}:\d{2}$/, "Enter a start time"),
  end_time: z.string().regex(/^\d{2}:\d{2}$/, "Enter an end time"),
  grace_in_min: z.number().int().min(0).max(240),
  grace_out_min: z.number().int().min(0).max(240),
  half_day_pct: z.number().int().min(1).max(100),
  is_night_shift: z.boolean(),
  weekly_offs: z.array(z.number().int().min(1).max(7)),
});
export type ShiftValues = z.infer<typeof shiftSchema>;

export const holidaySchema = z.object({
  location_id: z.string().min(1, "Choose a location"),
  date: z.string().min(1, "Choose the date"),
  name: z.string().trim().min(1, "Name is required").max(120),
});
export type HolidayValues = z.infer<typeof holidaySchema>;
