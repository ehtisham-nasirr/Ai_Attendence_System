import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import type { SettingItem } from "@/api/generated/model";
import { LiveFeedProvider } from "@/components/common/LiveFeedProvider";
import { SettingsGroupForm } from "@/components/settings/SettingsGroupForm";
import { DashboardPage } from "@/pages/dashboard/DashboardPage";
import { ok, page } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { server } from "@/test/server";

const items: SettingItem[] = [
  { key: "recognition.margin", group: "recognition", value: 0.08, default: 0.08, description: "Best minus second-best.", secret: false, is_set: true },
  { key: "retention.snapshot_days", group: "retention", value: 90, default: 90, description: "Snapshot retention.", secret: false, is_set: true },
];

describe("Settings (FR-38)", () => {
  it("sends only changed keys", async () => {
    let sent: unknown = null;
    server.use(
      http.put("*/api/v1/settings", async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json(ok(items, "Settings saved."));
      }),
    );
    renderWithProviders(<SettingsGroupForm items={items} />);
    const days = await screen.findByLabelText("Snapshot days");
    await userEvent.clear(days);
    await userEvent.type(days, "30");
    await userEvent.click(screen.getByRole("button", { name: "Save 1 change" }));
    await screen.findByRole("button", { name: /change|No changes/ });
    expect(sent).toEqual({ values: { "retention.snapshot_days": 30 } });
  });

  it("asks for confirmation before making recognition less strict", async () => {
    const put = vi.fn(() => HttpResponse.json(ok(items, "Settings saved.")));
    server.use(http.put("*/api/v1/settings", put));
    renderWithProviders(<SettingsGroupForm items={items} />);
    const margin = await screen.findByLabelText("Margin");
    await userEvent.clear(margin);
    await userEvent.type(margin, "0.05");
    await userEvent.click(screen.getByRole("button", { name: "Save 1 change" }));
    expect(await screen.findByText("Make recognition less strict?")).toBeInTheDocument();
    expect(put).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Lower and save" }));
    await vi.waitFor(() => expect(put).toHaveBeenCalledTimes(1));
  });

  it("shows the API's per-key validation errors", async () => {
    server.use(
      http.put("*/api/v1/settings", () =>
        HttpResponse.json(
          { success: false, message: "Validation failed.", errors: { "retention.snapshot_days": ["Input should be greater than 0"] } },
          { status: 422 },
        ),
      ),
    );
    renderWithProviders(<SettingsGroupForm items={items} />);
    const days = await screen.findByLabelText("Snapshot days");
    await userEvent.clear(days);
    await userEvent.type(days, "-1");
    await userEvent.click(screen.getByRole("button", { name: "Save 1 change" }));
    expect(await screen.findByText("Input should be greater than 0")).toBeInTheDocument();
  });
});

describe("Dashboard (§13 screen 2)", () => {
  it("shows the KPIs the API computed and the camera strip", async () => {
    vi.stubGlobal(
      "WebSocket",
      class {
        close() {}
      },
    );
    server.use(
      http.get("*/api/v1/dashboard/summary", () =>
        HttpResponse.json(
          ok({
            work_date: "2026-10-05",
            expected: 120,
            present: 97,
            late: 11,
            absent: 9,
            on_leave: 3,
            in_office_now: 88,
            unknown_today: 4,
            hourly_arrivals: [{ hour: 9, count: 60 }],
            departments: [{ department_id: 1, department_name: "Sales", present: 40, absent: 2, late: 5 }],
            cameras: [{ camera_id: 1, name: "Main entrance", status: "online", mode: "ACTIVE", fps_actual: 3.9 }],
            load_levels: { "node-1": 2 },
          }),
        ),
      ),
      http.get("*/api/v1/events", () => HttpResponse.json(page([]))),
      http.get("*/api/v1/cameras", () => HttpResponse.json(page([]))),
    );
    renderWithProviders(
      <LiveFeedProvider>
        <DashboardPage />
      </LiveFeedProvider>,
    );
    expect(await screen.findByText("97")).toBeInTheDocument();
    expect(screen.getByText("of 120 expected")).toBeInTheDocument();
    expect(screen.getByText("Main entrance")).toBeInTheDocument();
    expect(screen.getByText(/Reduced processing: node-1 level 2/)).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
