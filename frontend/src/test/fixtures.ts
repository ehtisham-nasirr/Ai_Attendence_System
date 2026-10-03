import type { EmployeeOut, UserProfile } from "@/api/generated/model";

export const hrUser: UserProfile = {
  id: 2,
  name: "Hina HR",
  username: "hina",
  email: "hina@example.com",
  role: "hr_admin",
  employee_id: null,
  permissions: [
    "employees:manage",
    "live:view",
    "attendance:view",
    "attendance:correct",
    "unknown_faces:review",
    "unknown_faces:assign",
    "events:view",
    "events:void",
    "reports:export",
    "dashboard:view",
    "organization:view",
  ],
  last_login_at: null,
  timezone: "Asia/Karachi",
};

export const employeeUser: UserProfile = {
  id: 9,
  name: "Ali Employee",
  username: "ali",
  email: "ali@example.com",
  role: "employee",
  employee_id: 41,
  permissions: ["attendance:view", "corrections:request", "reports:export"],
  last_login_at: null,
  timezone: "Asia/Karachi",
};

export function employee(overrides: Partial<EmployeeOut> = {}): EmployeeOut {
  return {
    id: 41,
    employee_code: "E-041",
    full_name: "Ayesha Khan",
    department_id: 1,
    department_name: "Sales",
    designation: "Executive",
    shift_id: 1,
    shift_name: "Day",
    location_id: 1,
    location_name: "HQ",
    email: null,
    phone: null,
    status: "active",
    consent_signed_at: "2026-09-01T07:00:00Z",
    deactivated_at: null,
    hr_external_id: null,
    enrolled_photos: 3,
    enrollment_complete: true,
    created_at: "2026-09-01T07:00:00Z",
    ...overrides,
  };
}

export function page<T>(data: T[], total = data.length, pageNumber = 1, pageSize = 20) {
  return { success: true, message: "ok", data, pagination: { page: pageNumber, page_size: pageSize, total } };
}

export function ok<T>(data: T, message = "ok") {
  return { success: true, message, data };
}
