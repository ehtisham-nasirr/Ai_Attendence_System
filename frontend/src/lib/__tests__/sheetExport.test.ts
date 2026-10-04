import { describe, expect, it } from "vitest";

import { toSheetRows, xlsxFileName, type SheetColumn } from "@/lib/sheetExport";

interface Row {
  name: string;
  status: "recognized" | "unknown";
  score: number | null;
  manual: boolean;
}

const columns: SheetColumn<Row>[] = [
  { header: "Name", value: (r) => r.name },
  { header: "Status", value: (r) => r.status, tone: (r) => (r.status === "recognized" ? "ok" : "warn") },
  { header: "Score", value: (r) => r.score },
  { header: "Manual", value: (r) => r.manual },
];

describe("Excel export of list views (Q62)", () => {
  it("keeps numbers, colours status cells and leaves empty cells uncoloured", () => {
    const rows = toSheetRows(columns, [
      { name: "Ayesha", status: "recognized", score: 0.82, manual: true },
      { name: "", status: "unknown", score: null, manual: false },
    ]);
    expect(rows[0]).toEqual([
      { value: "Ayesha" },
      { value: "recognized", tone: "ok" },
      { value: 0.82 },
      { value: "Yes" },
    ]);
    expect(rows[1]).toEqual([{ value: null }, { value: "unknown", tone: "warn" }, { value: null }, { value: null }]);
  });

  it("names the file .xlsx", () => {
    expect(xlsxFileName("events-2026-10-04.csv")).toBe("events-2026-10-04.xlsx");
    expect(xlsxFileName("audit-log")).toBe("audit-log.xlsx");
  });
});
