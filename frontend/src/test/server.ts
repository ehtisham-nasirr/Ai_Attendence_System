import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import { hrUser, ok, page } from "@/test/fixtures";

/** Default API: a signed-in HR user and empty reference lists. Tests override what they need. */
export const defaultHandlers = [
  http.get("*/api/v1/auth/me", () => HttpResponse.json(ok(hrUser))),
  http.get("*/api/v1/auth/options", () => HttpResponse.json(ok({ ldap_enabled: false }))),
  http.get("*/api/v1/departments", () => HttpResponse.json(page([{ id: 1, name: "Sales", code: "SAL", manager_user_id: null, created_at: "2026-01-01T00:00:00Z" }]))),
  http.get("*/api/v1/shifts", () => HttpResponse.json(page([]))),
  http.get("*/api/v1/locations", () => HttpResponse.json(page([]))),
];

export const server = setupServer(...defaultHandlers);
