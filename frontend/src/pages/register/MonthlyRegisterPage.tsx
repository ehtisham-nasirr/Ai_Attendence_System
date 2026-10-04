import type { ColumnDef } from "@tanstack/react-table";
import { CalendarDays } from "lucide-react";
import { useMemo } from "react";

import type { MonthlyRegisterParams, RegisterRow } from "@/api/generated/model";
import { MonthPicker } from "@/components/attendance/MonthPicker";
import { DataTable } from "@/components/common/DataTable";
import { EmptyState } from "@/components/common/EmptyState";
import { FilterSelect } from "@/components/common/FilterSelect";
import { PageHeader } from "@/components/common/PageHeader";
import { SearchInput } from "@/components/common/SearchInput";
import { useTimezone } from "@/hooks/useAuth";
import { exportRegister, useMonthlyRegister } from "@/hooks/useAttendance";
import { useDepartments } from "@/hooks/useOrganization";
import { useUrlState } from "@/hooks/useUrlState";
import { formatMinutes, todayIn } from "@/lib/format";
import { statusLetterLegend, type Tone } from "@/lib/labels";
import { currentMonth, monthRange, WEEKDAYS, weekdayIndex } from "@/lib/month";
import { cn } from "@/lib/utils";

const letterTone = new Map(statusLetterLegend.map((entry) => [entry.letter, entry.tone]));
const toneText: Record<Tone, string> = {
  ok: "text-status-ok",
  warn: "text-status-warn",
  bad: "text-status-bad",
  info: "text-status-info",
  neutral: "text-status-neutral",
  leave: "text-status-leave",
};

function letterOn(row: RegisterRow, day: string): { letter: string | null; manual: boolean } {
  const cell = row.days.find((d) => d.work_date === day);
  return { letter: cell?.letter ?? null, manual: cell?.is_manual ?? false };
}

/** §13 screen 8: employee × day grid with status letters and row totals (computed by the API). */
export function MonthlyRegisterPage() {
  const timezone = useTimezone();
  const url = useUrlState();
  const departments = useDepartments();
  const thisMonth = currentMonth(todayIn(timezone));
  const month = url.get("month") ?? thisMonth;
  const { days } = monthRange(month);
  const filters: MonthlyRegisterParams = {
    month,
    department_id: url.getNumber("department_id") ?? undefined,
    search: url.get("search") || undefined,
  };
  const pageSize = url.getNumber("page_size") ?? 50;
  const query = useMonthlyRegister({ ...filters, page: url.page, page_size: pageSize });

  const columns = useMemo<ColumnDef<RegisterRow>[]>(
    () => [
      {
        id: "employee",
        header: "Employee",
        meta: {
          className: "bg-card [thead_&]:bg-muted sticky left-0 z-10 min-w-44",
          exportValue: (r) => `${r.employee_code} ${r.employee_name}`,
        },
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
      ...days.map<ColumnDef<RegisterRow>>((day) => ({
        id: day,
        header: () => (
          <div className="text-center leading-tight">
            <div>{Number(day.slice(8))}</div>
            <div className="text-[10px] font-normal">{WEEKDAYS[weekdayIndex(day)].slice(0, 2)}</div>
          </div>
        ),
        meta: {
          className: "w-9 px-1 text-center",
          exportValue: (r) => letterOn(r, day).letter ?? "",
          exportTone: (r) => letterTone.get(letterOn(r, day).letter ?? ""),
        },
        cell: ({ row }) => {
          const { letter, manual } = letterOn(row.original, day);
          if (!letter) return <span className="text-muted-foreground">·</span>;
          return (
            <span
              className={cn("text-xs font-semibold", toneText[letterTone.get(letter) ?? "neutral"], manual && "underline")}
              title={manual ? "Includes a manual correction" : undefined}
            >
              {letter}
            </span>
          );
        },
      })),
      {
        id: "totals",
        header: "Totals",
        meta: {
          className: "min-w-40",
          exportValue: (r) =>
            Object.entries(r.totals)
              .map(([letter, count]) => `${letter}:${count}`)
              .join(" "),
        },
        cell: ({ row }) => (
          <div className="flex flex-wrap gap-x-2 text-xs">
            {statusLetterLegend
              .filter((entry) => row.original.totals[entry.letter])
              .map((entry) => (
                <span key={entry.letter} className={toneText[entry.tone]}>
                  {entry.letter} {row.original.totals[entry.letter]}
                </span>
              ))}
          </div>
        ),
      },
      {
        id: "worked",
        header: "Worked",
        meta: { exportValue: (r) => r.worked_minutes },
        cell: ({ row }) => <span className="tabular-nums whitespace-nowrap">{formatMinutes(row.original.worked_minutes)}</span>,
      },
    ],
    [days],
  );

  return (
    <>
      <PageHeader title="Monthly register" description="Status letter per employee per day." />
      <DataTable
        columns={columns}
        rows={query.data?.data}
        total={query.data?.pagination.total ?? 0}
        page={url.page}
        pageSize={pageSize}
        onPageChange={(page) => url.set({ page })}
        onPageSizeChange={(page_size) => url.set({ page_size })}
        isLoading={query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        getRowId={(row) => String(row.employee_id)}
        exportAll={() => exportRegister(filters)}
        exportFileName={`register-${month}.csv`}
        exportTitle={`Monthly register ${month}`}
        toolbar={
          <>
            <MonthPicker month={month} onChange={(next) => url.set({ month: next })} max={thisMonth} />
            <SearchInput value={url.get("search") ?? ""} onChange={(search) => url.set({ search })} placeholder="Search name or code" />
            <FilterSelect
              label="Department"
              allLabel="All departments"
              value={url.get("department_id")}
              options={(departments.data?.data ?? []).map((d) => ({ value: String(d.id), label: d.name }))}
              onChange={(department_id) => url.set({ department_id })}
            />
          </>
        }
        empty={<EmptyState icon={CalendarDays} title="No employees in this register" description="Change the month or filters." />}
      />
      <div className="text-muted-foreground mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs" aria-label="Legend">
        {statusLetterLegend.map((entry) => (
          <span key={entry.letter}>
            <span className={cn("font-semibold", toneText[entry.tone])}>{entry.letter}</span> {entry.label}
          </span>
        ))}
        <span>
          <span className="font-semibold underline">X</span> manual correction
        </span>
      </div>
    </>
  );
}
