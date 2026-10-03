import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { EmployeesPage } from "@/pages/employees/EmployeesPage";
import { employee, page } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { server } from "@/test/server";

describe("Employees (§13 screen 4)", () => {
  it("lists employees with enrollment and status as text", async () => {
    const seen: URLSearchParams[] = [];
    server.use(
      http.get("*/api/v1/employees", ({ request }) => {
        seen.push(new URL(request.url).searchParams);
        return HttpResponse.json(
          page([employee(), employee({ id: 42, employee_code: "E-042", full_name: "Bilal", enrolled_photos: 0, enrollment_complete: false, status: "inactive" })]),
        );
      }),
    );
    renderWithProviders(<EmployeesPage />, { route: "/employees" });
    const table = await screen.findByRole("table");
    expect(await within(table).findByText("Ayesha Khan")).toBeInTheDocument();
    expect(within(table).getByText("Enrolled 3 photos")).toBeInTheDocument();
    expect(within(table).getByText("Not enrolled")).toBeInTheDocument();
    expect(within(table).getByText("Inactive")).toBeInTheDocument();
    expect(seen[0].get("page")).toBe("1");
  });

  it("puts the search in the request", async () => {
    const searches: (string | null)[] = [];
    server.use(
      http.get("*/api/v1/employees", ({ request }) => {
        searches.push(new URL(request.url).searchParams.get("search"));
        return HttpResponse.json(page([]));
      }),
    );
    renderWithProviders(<EmployeesPage />, { route: "/employees" });
    await userEvent.type(await screen.findByLabelText("Search name or code"), "ayesha");
    await screen.findByText("No employees match these filters", {}, { timeout: 2_000 });
    expect(searches).toContain("ayesha");
  });

  it("explains the next step when there are no employees", async () => {
    server.use(http.get("*/api/v1/employees", () => HttpResponse.json(page([]))));
    renderWithProviders(<EmployeesPage />, { route: "/employees" });
    expect(await screen.findByText("No employees yet")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Add employee" }).length).toBeGreaterThan(0);
  });

  it("shows an error with retry when the API fails", async () => {
    server.use(
      http.get("*/api/v1/employees", () =>
        HttpResponse.json({ success: false, message: "Database unavailable.", errors: {} }, { status: 503 }),
      ),
    );
    renderWithProviders(<EmployeesPage />, { route: "/employees" });
    expect(await screen.findByText("Database unavailable.", {}, { timeout: 4_000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
