/** Excel export of list views with the status colours of the screen (§13 "export on every list", Q62). */
import { exportSheet } from "@/api/generated/endpoints";
import type { SheetCell } from "@/api/generated/model";
import { downloadBlob } from "@/lib/csv";
import type { Tone } from "@/lib/labels";

export type ExportValue = string | number | boolean | null | undefined;

export interface SheetColumn<T> {
  header: string;
  value: (row: T) => ExportValue;
  /** Colour of the cell, the same tone as the badge on screen. */
  tone?: (row: T) => Tone | undefined;
}

function cellValue(value: ExportValue): string | number | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "boolean") return value ? "Yes" : null;
  return value;
}

export function toSheetRows<T>(columns: SheetColumn<T>[], rows: T[]): SheetCell[][] {
  return rows.map((row) =>
    columns.map((column) => {
      const value = cellValue(column.value(row));
      const tone = value === null ? undefined : column.tone?.(row);
      return tone ? { value, tone } : { value };
    }),
  );
}

/** "events-2026-10-04.csv" -> "events-2026-10-04.xlsx" */
export function xlsxFileName(fileName: string): string {
  return `${fileName.replace(/\.[^.]+$/, "")}.xlsx`;
}

export async function downloadSheet<T>(
  title: string,
  fileName: string,
  columns: SheetColumn<T>[],
  rows: T[],
): Promise<void> {
  const name = xlsxFileName(fileName);
  const blob = (await exportSheet(
    { title, file_name: name, columns: columns.map((c) => c.header), rows: toSheetRows(columns, rows) },
    { responseType: "blob" },
  )) as unknown as Blob;
  downloadBlob(blob, name);
}
