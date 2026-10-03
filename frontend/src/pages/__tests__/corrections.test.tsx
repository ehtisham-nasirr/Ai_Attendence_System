import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { AttendanceDayOut } from "@/api/generated/model";
import { AttendanceDayDialog } from "@/components/attendance/AttendanceDayDialog";
import { CorrectionsPage } from "@/pages/corrections/CorrectionsPage";
import { employeeUser, ok, page } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { server } from "@/test/server";

const day: AttendanceDayOut = {
  id: 77,
  employee_id: 41,
  employee_code: "E-041",
  employee_name: "Ayesha Khan",
  department_id: 1,
  department_name: "Sales",
  work_date: "2026-10-05",
  shift_id: 1,
  shift_name: "Day",
  check_in_at: "2026-10-05T04:40:00Z",
  check_out_at: null,
  check_in_event_id: 900,
  check_out_event_id: null,
  worked_minutes: 0,
  late_minutes: 25,
  early_minutes: 0,
  overtime_minutes: 0,
  status: "late",
  status_letter: "L",
  is_manual: false,
  finalized_at: null,
};

describe("correcting a day (FR-25, FR-26, ADR-0004)", () => {
  it("HR applies a check-out in local time; the API receives UTC", async () => {
    let body: Record<string, string> | null = null;
    server.use(
      http.post("*/api/v1/attendance/77/corrections", async ({ request }) => {
        body = (await request.json()) as Record<string, string>;
        return HttpResponse.json(ok({ correction: {}, attendance: day }, "Correction applied."));
      }),
    );
    renderWithProviders(<AttendanceDayDialog day={day} onOpenChange={() => {}} />);
    expect(await screen.findByText("09:40")).toBeInTheDocument(); // 04:40 UTC shown in Pakistan time
    expect(screen.getAllByText("Late").length).toBeGreaterThan(0); // status badge
    await screen.findByRole("button", { name: "Apply correction" }); // form appears once the user's role is known
    await userEvent.click(screen.getByRole("combobox", { name: "What is wrong?" }));
    await userEvent.click(await screen.findByRole("option", { name: "Check-out" }));
    await userEvent.type(screen.getByLabelText("Time"), "18:30");
    await userEvent.type(screen.getByLabelText("Reason"), "Exit camera was offline");
    await userEvent.click(screen.getByRole("button", { name: "Apply correction" }));
    await screen.findByRole("button", { name: "Apply correction" });
    expect(body).toEqual({ field: "check_out_at", new_value: "2026-10-05T13:30:00.000Z", reason: "Exit camera was offline" });
  });

  it("an employee sends a request instead, and needs a reason", async () => {
    server.use(http.get("*/api/v1/auth/me", () => HttpResponse.json(ok(employeeUser))));
    renderWithProviders(<AttendanceDayDialog day={day} onOpenChange={() => {}} />);
    const send = await screen.findByRole("button", { name: "Send request" });
    expect(screen.queryByRole("button", { name: "Apply correction" })).not.toBeInTheDocument();
    await userEvent.click(send);
    expect(await screen.findByText("Give a reason (at least 5 characters)")).toBeInTheDocument();
  });

  it("shows field errors from the API under the time", async () => {
    server.use(
      http.post("*/api/v1/attendance/77/corrections", () =>
        HttpResponse.json(
          { success: false, message: "Validation failed.", errors: { new_value: ["The time does not fall within this work day."] } },
          { status: 422 },
        ),
      ),
    );
    renderWithProviders(<AttendanceDayDialog day={day} onOpenChange={() => {}} />);
    await userEvent.type(await screen.findByLabelText("Time"), "08:00");
    await userEvent.type(screen.getByLabelText("Reason"), "Came early really");
    await userEvent.click(screen.getByRole("button", { name: "Apply correction" }));
    expect(await screen.findByText("The time does not fall within this work day.")).toBeInTheDocument();
  });
});

describe("Corrections screen (§13 screen 11)", () => {
  it("shows old and new values side by side and approves with a comment", async () => {
    let decided: unknown = null;
    server.use(
      http.get("*/api/v1/corrections", () =>
        HttpResponse.json(
          page([
            {
              id: 5,
              attendance_day_id: 77,
              employee_id: 41,
              employee_code: "E-041",
              employee_name: "Ayesha Khan",
              work_date: "2026-10-05",
              field: "status",
              old_value: "absent",
              new_value: "present",
              reason: "Was at a client site",
              status: "pending",
              requested_by: 9,
              requested_by_name: "Ayesha Khan",
              approved_by: null,
              approved_by_name: null,
              approved_at: null,
              review_comment: null,
              created_at: "2026-10-05T10:00:00Z",
            },
          ]),
        ),
      ),
      http.post("*/api/v1/corrections/5/approve", async ({ request }) => {
        decided = await request.json();
        return HttpResponse.json(ok({ correction: {}, attendance: day }, "Correction approved."));
      }),
    );
    renderWithProviders(<CorrectionsPage />, { route: "/corrections" });
    expect(await screen.findByText("Absent")).toBeInTheDocument();
    expect(screen.getByText("Present")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    await userEvent.type(await screen.findByLabelText(/Comment/), "Confirmed with manager");
    await userEvent.click(screen.getAllByRole("button", { name: "Approve" }).at(-1) as HTMLElement);
    await screen.findByText("Absent");
    expect(decided).toEqual({ comment: "Confirmed with manager" });
  });
});
