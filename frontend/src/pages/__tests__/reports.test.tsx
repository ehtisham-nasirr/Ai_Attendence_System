import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ReportOut } from "@/api/generated/model";
import { ApiKeysCard } from "@/components/settings/IntegrationCard";
import * as reportHooks from "@/hooks/useReports";
import { ReportsPage } from "@/pages/reports/ReportsPage";
import { hrUser, ok } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { server } from "@/test/server";

const report: ReportOut = {
  report_type: "late_arrivals",
  title: "Late arrivals",
  date_from: "2026-09-01",
  date_to: "2026-09-30",
  columns: [
    { key: "work_date", label: "Date", kind: "date" },
    { key: "employee_name", label: "Employee", kind: "text" },
    { key: "check_in_at", label: "Check-in", kind: "time" },
    { key: "late_minutes", label: "Late", kind: "minutes" },
  ],
  rows: [{ work_date: "2026-09-02", employee_name: "Ayesha Khan", check_in_at: "2026-09-02T04:40:00Z", late_minutes: 25, _tz: "Asia/Karachi" }],
  total_rows: 1,
  truncated: false,
  summary: [
    { label: "Late days", value: 1, kind: "count" },
    { label: "Total late", value: 25, kind: "minutes" },
  ],
  chart: { x_key: "work_date", series: [{ key: "late", label: "Late arrivals" }], data: [{ work_date: "2026-09-02", late: 1 }] },
  timezone: "Asia/Karachi",
};

describe("Reports (§13 screen 12, FR-30, FR-31)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("previews a report with filters from the URL, formatted for display", async () => {
    let query = new URLSearchParams();
    server.use(
      http.get("*/api/v1/reports/late_arrivals", ({ request }) => {
        query = new URL(request.url).searchParams;
        return HttpResponse.json(ok(report));
      }),
    );
    renderWithProviders(<ReportsPage />, { route: "/reports?type=late_arrivals&from=2026-09-01&to=2026-09-30" });
    await userEvent.click(await screen.findByRole("button", { name: "Run report" }));
    expect(await screen.findByText("Ayesha Khan")).toBeInTheDocument();
    expect(screen.getByText("09:40")).toBeInTheDocument(); // 04:40 UTC in Pakistan
    expect(screen.getAllByText("25m").length).toBe(2); // summary card and row
    expect(query.get("date_from")).toBe("2026-09-01");
    expect(query.get("format")).toBeNull();
  });

  it("exports as a job and downloads the file when it is ready", async () => {
    // Blob responses do not work under jsdom + MSW; the browser run (e2e) covers the real download.
    const download = vi.spyOn(reportHooks, "downloadJobFile").mockResolvedValue();
    let polls = 0;
    server.use(
      http.get("*/api/v1/reports/late_arrivals", ({ request }) =>
        new URL(request.url).searchParams.get("format") === "xlsx"
          ? HttpResponse.json(ok({ job_id: "job-1" }, "Export started."), { status: 202 })
          : HttpResponse.json(ok(report)),
      ),
      http.get("*/api/v1/jobs/job-1", () => {
        polls += 1;
        const status = polls < 2 ? "running" : "succeeded";
        return HttpResponse.json(ok({ id: "job-1", kind: "report_export", status, message: "1 rows", file_available: status === "succeeded" }));
      }),
    );
    renderWithProviders(<ReportsPage />, { route: "/reports?type=late_arrivals&from=2026-09-01&to=2026-09-30&run=1" });
    await userEvent.click(await screen.findByRole("button", { name: "Export Excel" }));
    expect(await screen.findByRole("button", { name: "Preparing Excel…" })).toBeDisabled();
    await waitFor(() => expect(download).toHaveBeenCalled(), { timeout: 6_000 });
    expect(download).toHaveBeenCalledWith("job-1", "facetrack-late_arrivals-20260901-20260930.xlsx");
  }, 10_000);

  it("asks for the employee before running employee history", async () => {
    renderWithProviders(<ReportsPage />, { route: "/reports?type=employee_history&run=1" });
    expect(await screen.findByText("Choose the employee first.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run report" })).toBeDisabled();
  });
});

describe("API keys (FR-34)", () => {
  it("shows a new key once", async () => {
    server.use(
      http.get("*/api/v1/auth/me", () => HttpResponse.json(ok({ ...hrUser, role: "super_admin", permissions: ["settings:manage"] }))),
      http.get("*/api/v1/api-clients", () => HttpResponse.json(ok([]))),
      http.post("*/api/v1/api-clients", () =>
        HttpResponse.json(
          ok({
            client: { id: 1, name: "Payroll", key_prefix: "ab12cd34", scopes: ["attendance:read"], is_active: true, last_used_at: null, created_at: "2026-10-04T00:00:00Z" },
            api_key: "ft_ab12cd34_secret-value",
          }),
          { status: 201 },
        ),
      ),
    );
    renderWithProviders(<ApiKeysCard />);
    await userEvent.type(await screen.findByLabelText("New key for"), "Payroll");
    await userEvent.click(screen.getByRole("button", { name: "Create key" }));
    expect(await screen.findByDisplayValue("ft_ab12cd34_secret-value")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByDisplayValue("ft_ab12cd34_secret-value")).not.toBeInTheDocument();
  });
});
