import { z } from "zod";

import { passwordSchema } from "@/lib/schemas/auth";

export function userSchema(isNew: boolean) {
  return z
    .object({
      name: z.string().trim().min(1, "Name is required").max(200),
      username: z
        .string()
        .trim()
        .min(3, "At least 3 characters")
        .max(120)
        .regex(/^[A-Za-z0-9._@-]+$/, "Letters, digits, dot, @, dash or underscore"),
      email: z.email("Enter a valid email address"),
      role: z.enum(["super_admin", "hr_admin", "department_manager", "operator", "employee"]),
      auth_provider: z.enum(["local", "ldap"]),
      employee_id: z.number().int().nullable(),
      employee_label: z.string(),
      password: z.union([z.literal(""), passwordSchema]),
      is_active: z.boolean(),
    })
    .superRefine((values, ctx) => {
      if (isNew && values.auth_provider === "local" && !values.password) {
        ctx.addIssue({ code: "custom", path: ["password"], message: "Set a first password" });
      }
      if (values.role === "employee" && values.employee_id === null) {
        ctx.addIssue({ code: "custom", path: ["employee_id"], message: "Link the account to an employee" });
      }
    });
}
export type UserValues = z.infer<ReturnType<typeof userSchema>>;
