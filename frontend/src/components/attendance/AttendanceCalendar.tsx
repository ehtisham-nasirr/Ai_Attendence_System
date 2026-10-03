import { useMemo } from "react";

import type { AttendanceDayOut } from "@/api/generated/model";
import { ErrorState } from "@/components/common/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { useAttendance } from "@/hooks/useAttendance";
import { useTimezone } from "@/hooks/useAuth";
import { formatMinutes, formatTime } from "@/lib/format";
import { attendanceStatusLabel, type Tone } from "@/lib/labels";
import { monthRange, WEEKDAYS, weekdayIndex } from "@/lib/month";
import { cn } from "@/lib/utils";

const toneBorder: Record<Tone, string> = {
  ok: "border-l-status-ok",
  warn: "border-l-status-warn",
  bad: "border-l-status-bad",
  info: "border-l-status-info",
  neutral: "border-l-status-neutral",
  leave: "border-l-status-leave",
};

/**
 * Month calendar of one employee's attendance (§13 screens 5 and 14). Shows what the API computed;
 * clicking a day with a record calls `onSelect` (details / correction request).
 */
export function AttendanceCalendar({
  employeeId,
  month,
  onSelect,
}: {
  employeeId?: number;
  month: string;
  onSelect?: (day: AttendanceDayOut) => void;
}) {
  const timezone = useTimezone();
  const { first, last, days } = monthRange(month);
  const query = useAttendance({ employee_id: employeeId, date_from: first, date_to: last, page: 1, page_size: 62 });
  const byDate = useMemo(() => new Map((query.data?.data ?? []).map((d) => [d.work_date, d])), [query.data]);

  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const leading = weekdayIndex(first);
  return (
    <div className="space-y-2">
      <div className="text-muted-foreground grid grid-cols-7 gap-1 text-center text-xs font-medium">
        {WEEKDAYS.map((day) => (
          <div key={day}>{day}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {Array.from({ length: leading }, (_, i) => (
          <div key={`pad-${i}`} />
        ))}
        {days.map((day) => {
          if (query.isPending) return <Skeleton key={day} className="h-20" />;
          const record = byDate.get(day);
          const status = record?.status ? attendanceStatusLabel[record.status] : null;
          const content = (
            <>
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold">{Number(day.slice(8))}</span>
                {record?.is_manual && <span className="text-muted-foreground text-[10px]">manual</span>}
              </div>
              {status && <p className="truncate text-xs font-medium">{status.label}</p>}
              {record?.check_in_at && (
                <p className="text-muted-foreground truncate text-[11px]">
                  {formatTime(record.check_in_at, timezone)}–{formatTime(record.check_out_at, timezone)}
                </p>
              )}
              {record && record.worked_minutes > 0 && (
                <p className="text-muted-foreground text-[11px]">{formatMinutes(record.worked_minutes)}</p>
              )}
            </>
          );
          const className = cn(
            "bg-card flex h-20 flex-col gap-0.5 rounded-md border border-l-4 p-1.5 text-left",
            status ? toneBorder[status.tone] : "border-l-border",
          );
          return record && onSelect ? (
            <button
              key={day}
              type="button"
              className={cn(className, "hover:bg-muted/60 focus-visible:ring-ring/50 focus-visible:ring-2")}
              aria-label={`${day}: ${status?.label ?? "no status yet"}`}
              onClick={() => onSelect(record)}
            >
              {content}
            </button>
          ) : (
            <div key={day} className={className} aria-label={`${day}: ${status?.label ?? "no record"}`}>
              {content}
            </div>
          );
        })}
      </div>
    </div>
  );
}
