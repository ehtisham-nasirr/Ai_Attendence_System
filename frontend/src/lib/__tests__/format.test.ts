import { describe, expect, it } from "vitest";

import { formatDate, formatMinutes, formatTime, localToUtcIso, todayIn, utcToLocalTime } from "@/lib/format";
import { monthRange, nextDay, shiftMonth, weekdayIndex } from "@/lib/month";

describe("time display (UTC from the API, shown in the configured zone)", () => {
  it("shows Pakistan time", () => {
    expect(formatTime("2026-10-05T04:05:00Z", "Asia/Karachi")).toBe("09:05");
    expect(formatTime(null)).toBe("—");
  });

  it("converts a local wall-clock time back to UTC for the API", () => {
    expect(localToUtcIso("2026-10-05", "09:05", "Asia/Karachi")).toBe("2026-10-05T04:05:00.000Z");
    expect(localToUtcIso("2026-10-06", "02:00", "Asia/Karachi")).toBe("2026-10-05T21:00:00.000Z");
    expect(localToUtcIso("2026-07-01", "09:00", "Europe/London")).toBe("2026-07-01T08:00:00.000Z");
    expect(utcToLocalTime("2026-10-05T04:05:00Z", "Asia/Karachi")).toBe("09:05");
  });

  it("finds today in the zone, not the browser's", () => {
    expect(todayIn("Asia/Karachi", new Date("2026-10-04T20:30:00Z"))).toBe("2026-10-05");
    expect(todayIn("UTC", new Date("2026-10-04T20:30:00Z"))).toBe("2026-10-04");
  });

  it("formats calendar dates without shifting them", () => {
    expect(formatDate("2026-10-05")).toBe("05 Oct 2026");
  });

  it("formats API minutes", () => {
    expect(formatMinutes(0)).toBe("0m");
    expect(formatMinutes(45)).toBe("45m");
    expect(formatMinutes(485)).toBe("8h 05m");
  });
});

describe("month helpers", () => {
  it("handles month and year boundaries", () => {
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(monthRange("2028-02").days).toHaveLength(29);
    expect(nextDay("2026-12-31")).toBe("2027-01-01");
    expect(weekdayIndex("2026-10-05")).toBe(0); // a Monday
  });
});
