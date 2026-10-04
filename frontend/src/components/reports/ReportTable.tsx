import type { AttendanceStatus, ReportColumn, ReportOut } from "@/api/generated/model";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, formatMinutes, formatTime } from "@/lib/format";
import { attendanceStatusLabel } from "@/lib/labels";

function Cell({ column, row, timezone }: { column: ReportColumn; row: Record<string, unknown>; timezone: string }) {
  const value = row[column.key];
  if (value === null || value === undefined || value === "") return <span className="text-muted-foreground">—</span>;
  switch (column.kind) {
    case "time":
      return <span className="tabular-nums">{formatTime(String(value), typeof row._tz === "string" ? row._tz : timezone)}</span>;
    case "date":
      return <span className="whitespace-nowrap">{formatDate(String(value))}</span>;
    case "minutes":
      return <span className="tabular-nums">{formatMinutes(Number(value))}</span>;
    case "status": {
      const status = attendanceStatusLabel[value as AttendanceStatus];
      return status ? <StatusBadge label={status.label} tone={status.tone} /> : <>{String(value)}</>;
    }
    case "bool":
      return <>{value ? "Yes" : ""}</>;
    case "code":
      return <span className="tabular-nums">{String(value)}</span>;
    default:
      return <>{String(value)}</>;
  }
}

/** Preview of a report's rows exactly as the API computed them. */
export function ReportTable({ report }: { report: ReportOut }) {
  const compact = report.columns.some((c) => c.kind === "letter");
  return (
    <div className="bg-card rounded-lg border">
      <Table className={compact ? "text-xs" : undefined}>
        <TableHeader>
          <TableRow>
            {report.columns.map((column) => (
              <TableHead key={column.key} className={column.kind === "letter" ? "w-7 px-1 text-center" : undefined}>
                {column.label}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {report.rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={report.columns.length} className="text-muted-foreground py-10 text-center">
                No rows match these filters.
              </TableCell>
            </TableRow>
          ) : (
            report.rows.map((row, index) => (
              <TableRow key={index}>
                {report.columns.map((column) => (
                  <TableCell key={column.key} className={column.kind === "letter" ? "px-1 text-center" : undefined}>
                    <Cell column={column} row={row} timezone={report.timezone} />
                  </TableCell>
                ))}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}
