import type { ColumnDef } from "@tanstack/react-table";
import { CalendarPlus, ClipboardCheck, Pencil } from "lucide-react";
import { useMemo, useState } from "react";

import type { AttendanceDayOut, AttendanceStatus, ListAttendanceParams } from "@/api/generated/model";
import { AttendanceDayDialog } from "@/components/attendance/AttendanceDayDialog";
import { ManualEntryDialog } from "@/components/attendance/ManualEntryDialog";
import { SnapshotTime } from "@/components/attendance/SnapshotTime";
import { DataTable } from "@/components/common/DataTable";
import { EmptyState } from "@/components/common/EmptyState";
import { FilterSelect } from "@/components/common/FilterSelect";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { exportAttendance, useAttendance } from "@/hooks/useAttendance";
import { useTimezone } from "@/hooks/useAuth";
import { useDepartments } from "@/hooks/useOrganization";
import { useUrlState } from "@/hooks/useUrlState";
import { formatMinutes, formatTime, todayIn } from "@/lib/format";
import { attendanceStatusLabel } from "@/lib/labels";

/** §13 screen 7. */
export function AttendancePage() {
  const timezone = useTimezone();
  const url = useUrlState();
  const departments = useDepartments();
  const [selected, setSelected] = useState<AttendanceDayOut | null>(null);
  const [adding, setAdding] = useState(false);
  const date = url.get("date") ?? todayIn(timezone);
  const filters: ListAttendanceParams = {
    date_from: date,
    date_to: date,
    department_id: url.getNumber("department_id") ?? undefined,
    status: (url.get("status") as AttendanceStatus | null) ?? undefined,
    sort: url.sort ?? undefined,
  };
  const query = useAttendance({ ...filters, page: url.page, page_size: url.pageSize });

  const columns = useMemo<ColumnDef<AttendanceDayOut>[]>(
    () => [
      {
        id: "employee",
        header: "Employee",
        meta: { sortKey: "employee_code", exportValue: (d) => `${d.employee_code} ${d.employee_name}` },
        cell: ({ row }) => (
          <div>
            <p className="font-medium">{row.original.employee_name}</p>
            <p className="text-muted-foreground text-[12px] leading-4">
              <span className="tabular-nums">{row.original.employee_code}</span>
              {row.original.department_name && ` · ${row.original.department_name}`}
            </p>
          </div>
        ),
      },
      { id: "shift", header: "Shift", meta: { exportValue: (d) => d.shift_name ?? "" }, cell: ({ row }) => row.original.shift_name ?? "—" },
      {
        id: "check_in",
        header: "Check-in",
        meta: { sortKey: "check_in_at", exportValue: (d) => formatTime(d.check_in_at, timezone) },
        cell: ({ row }) => (
          <SnapshotTime
            time={row.original.check_in_at}
            eventId={row.original.check_in_event_id}
            timezone={timezone}
            name={row.original.employee_name}
          />
        ),
      },
      {
        id: "check_out",
        header: "Check-out",
        meta: { sortKey: "check_out_at", exportValue: (d) => formatTime(d.check_out_at, timezone) },
        cell: ({ row }) => (
          <SnapshotTime
            time={row.original.check_out_at}
            eventId={row.original.check_out_event_id}
            timezone={timezone}
            name={row.original.employee_name}
          />
        ),
      },
      {
        id: "worked",
        header: "Worked",
        meta: { exportValue: (d) => d.worked_minutes },
        cell: ({ row }) => <span className="tabular-nums">{formatMinutes(row.original.worked_minutes)}</span>,
      },
      {
        id: "late_early",
        header: "Late / early",
        meta: { sortKey: "late_minutes", exportValue: (d) => `${d.late_minutes}/${d.early_minutes}` },
        cell: ({ row }) => (
          <span className="tabular-nums">
            {row.original.late_minutes ? formatMinutes(row.original.late_minutes) : "—"} /{" "}
            {row.original.early_minutes ? formatMinutes(row.original.early_minutes) : "—"}
          </span>
        ),
      },
      {
        id: "status",
        header: "Status",
        meta: {
          sortKey: "status",
          exportValue: (d) => (d.status ? attendanceStatusLabel[d.status].label : ""),
          exportTone: (d) => (d.status ? attendanceStatusLabel[d.status].tone : undefined),
        },
        cell: ({ row }) => {
          const status = row.original.status ? attendanceStatusLabel[row.original.status] : null;
          return (
            <div className="flex flex-wrap items-center gap-1">
              {status ? <StatusBadge label={status.label} tone={status.tone} /> : <span className="text-muted-foreground">—</span>}
              {row.original.is_manual && <StatusBadge label="Manual" tone="info" />}
            </div>
          );
        },
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="sm"
            aria-label={`Correct attendance of ${row.original.employee_name}`}
            onClick={(event) => {
              event.stopPropagation();
              setSelected(row.original);
            }}
          >
            <Pencil aria-hidden /> Correct
          </Button>
        ),
      },
    ],
    [timezone],
  );

  return (
    <>
      <PageHeader
        title="Attendance"
        description="Daily attendance as computed from recognitions, leave, holidays and corrections."
        actions={
          <Button onClick={() => setAdding(true)}>
            <CalendarPlus aria-hidden /> Add manual entry
          </Button>
        }
      />
      <DataTable
        columns={columns}
        rows={query.data?.data}
        total={query.data?.pagination.total ?? 0}
        page={url.page}
        pageSize={url.pageSize}
        onPageChange={(page) => url.set({ page })}
        onPageSizeChange={(page_size) => url.set({ page_size })}
        sort={url.sort}
        onSortChange={(sort) => url.set({ sort })}
        isLoading={query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        getRowId={(row) => String(row.id)}
        onRowClick={setSelected}
        exportAll={() => exportAttendance(filters)}
        exportFileName={`attendance-${date}.csv`}
        exportTitle={`Attendance ${date}`}
        toolbar={
          <>
            <Input
              type="date"
              aria-label="Date"
              className="w-full sm:w-44"
              value={date}
              max={todayIn(timezone)}
              onChange={(event) => url.set({ date: event.target.value || null })}
            />
            <FilterSelect
              label="Department"
              allLabel="All departments"
              value={url.get("department_id")}
              options={(departments.data?.data ?? []).map((d) => ({ value: String(d.id), label: d.name }))}
              onChange={(department_id) => url.set({ department_id })}
            />
            <FilterSelect
              label="Status"
              allLabel="Any status"
              value={url.get("status")}
              options={(Object.keys(attendanceStatusLabel) as AttendanceStatus[]).map((s) => ({
                value: s,
                label: attendanceStatusLabel[s].label,
              }))}
              onChange={(status) => url.set({ status })}
            />
          </>
        }
        empty={
          <EmptyState
            icon={ClipboardCheck}
            title="No attendance for this day yet"
            description="Records appear when employees are recognised. Absent days are added when the day closes."
            action={
              <Button variant="outline" onClick={() => setAdding(true)}>
                Add manual entry
              </Button>
            }
          />
        }
      />
      <AttendanceDayDialog day={selected} onOpenChange={(open) => !open && setSelected(null)} />
      <ManualEntryDialog open={adding} onOpenChange={setAdding} defaultDate={date} />
    </>
  );
}
