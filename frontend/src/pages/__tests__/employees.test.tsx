import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import type { EmployeeOut } from "@/api/generated/model";
import * as sheetExport from "@/lib/sheetExport";
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

  it("exports the filtered list as an Excel file with status colours (Q62)", async () => {
    server.use(
      http.get("*/api/v1/employees", () =>
        HttpResponse.json(page([employee(), employee({ id: 42, employee_code: "E-042", full_name: "Bilal", status: "inactive" })])),
      ),
    );
    const download = vi.spyOn(sheetExport, "downloadSheet").mockResolvedValue();
    renderWithProviders(<EmployeesPage />, { route: "/employees" });
    await screen.findByText("Bilal");
    await userEvent.click(screen.getByRole("button", { name: "Export Excel" }));
    await waitFor(() => expect(download).toHaveBeenCalled());
    const [title, fileName, columns, rows] = download.mock.calls[0] as Parameters<typeof sheetExport.downloadSheet<EmployeeOut>>;
    expect([title, sheetExport.xlsxFileName(fileName)]).toEqual(["Employees", "employees.xlsx"]);
    const status = columns.findIndex((c) => c.header === "Status");
    expect(sheetExport.toSheetRows(columns, rows).map((row) => row[status])).toEqual([
      { value: "Active", tone: "ok" },
      { value: "Inactive", tone: "neutral" },
    ]);
    expect(screen.getByRole("button", { name: "CSV" })).toBeInTheDocument();
  });
});
