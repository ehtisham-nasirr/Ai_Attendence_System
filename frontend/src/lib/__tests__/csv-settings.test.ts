import { describe, expect, it } from "vitest";

import { toCsv } from "@/lib/csv";
import { lowersStrictness, settingKind } from "@/lib/settingsMeta";

describe("toCsv", () => {
  it("quotes, escapes and neutralises spreadsheet formulas", () => {
    const csv = toCsv(
      [
        { header: "Name", value: (r: { name: string }) => r.name },
        { header: "Note", value: () => "=HYPERLINK(\"x\")" },
      ],
      [{ name: 'Khan, "Ali"' }],
    );
    expect(csv.startsWith("﻿Name,Note\r\n")).toBe(true);
    expect(csv).toContain('"Khan, ""Ali"""');
    expect(csv).toContain(`"'=HYPERLINK(""x"")"`);
  });
});

describe("settings editing", () => {
  it("picks the input for each key", () => {
    expect(settingKind("attendance.day_close_time", "02:00", false)).toBe("time");
    expect(settingKind("notifications.hr_emails", [], false)).toBe("emails");
    expect(settingKind("integration.payroll_webhook_url", "", true)).toBe("secret");
    expect(settingKind("attendance.checkin_camera_roles", [], false)).toBe("roles");
    expect(settingKind("recognition.margin", 0.08, false)).toBe("number");
    expect(settingKind("retention.snapshot_days", 90, false)).toBe("integer");
    expect(settingKind("notifications.report_schedules", [], false)).toBe("hidden");
  });

  it("flags only changes that make recognition less strict", () => {
    expect(lowersStrictness("recognition.margin", 0.08, 0.05)).toBe(true);
    expect(lowersStrictness("recognition.margin", 0.08, 0.1)).toBe(false);
    expect(lowersStrictness("recognition.match_thresholds", { sface: 0.36 }, { sface: 0.3 })).toBe(true);
    expect(lowersStrictness("recognition.match_thresholds", { sface: 0.36 }, { sface: 0.4 })).toBe(false);
    expect(lowersStrictness("retention.snapshot_days", 90, 30)).toBe(false);
  });
});
