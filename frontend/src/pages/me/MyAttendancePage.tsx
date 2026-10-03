import { ClipboardList } from "lucide-react";
import { useState } from "react";

import type { AttendanceDayOut } from "@/api/generated/model";
import { AttendanceCalendar } from "@/components/attendance/AttendanceCalendar";
import { AttendanceDayDialog } from "@/components/attendance/AttendanceDayDialog";
import { MonthPicker } from "@/components/attendance/MonthPicker";
import { CorrectionCard } from "@/components/corrections/CorrectionCard";
import { EmptyState } from "@/components/common/EmptyState";
import { PageHeader } from "@/components/common/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCorrections, useMonthlyRegister } from "@/hooks/useAttendance";
import { useAuth } from "@/hooks/useAuth";
import { useUrlState } from "@/hooks/useUrlState";
import { formatMinutes, todayIn } from "@/lib/format";
import { statusLetterLegend } from "@/lib/labels";
import { currentMonth } from "@/lib/month";

/** §13 screen 14 (employee): own calendar, hours and correction requests. */
export function MyAttendancePage() {
  const { user, timezone } = useAuth();
  const url = useUrlState();
  const thisMonth = currentMonth(todayIn(timezone));
  const month = url.get("month") ?? thisMonth;
  const [selected, setSelected] = useState<AttendanceDayOut | null>(null);
  // The register endpoint returns only the employee's own row for this role.
  const register = useMonthlyRegister({ month, page: 1, page_size: 1 });
  const corrections = useCorrections({ page: 1, page_size: 20, sort: "-created_at" });
  const row = register.data?.data[0];

  return (
    <>
      <PageHeader
        title="My attendance"
        description={`Hello ${user?.name ?? ""}. Click a day to see details or ask for a correction.`}
      />
      <div className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <MonthPicker month={month} onChange={(next) => url.set({ month: next })} max={thisMonth} />
          <AttendanceCalendar employeeId={user?.employee_id ?? undefined} month={month} onSelect={setSelected} />
        </div>
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">This month</CardTitle>
            </CardHeader>
            <CardContent>
              {register.isPending ? (
                <Skeleton className="h-24" />
              ) : row ? (
                <dl className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <dt className="text-muted-foreground text-xs">Worked</dt>
                    <dd className="font-medium">{formatMinutes(row.worked_minutes)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground text-xs">Late</dt>
                    <dd className="font-medium">{formatMinutes(row.late_minutes)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground text-xs">Overtime</dt>
                    <dd className="font-medium">{formatMinutes(row.overtime_minutes)}</dd>
                  </div>
                  {statusLetterLegend
                    .filter((entry) => row.totals[entry.letter])
                    .map((entry) => (
                      <div key={entry.letter}>
                        <dt className="text-muted-foreground text-xs">{entry.label}</dt>
                        <dd className="font-medium">{row.totals[entry.letter]} days</dd>
                      </div>
                    ))}
                </dl>
              ) : (
                <p className="text-muted-foreground text-sm">No attendance this month yet.</p>
              )}
            </CardContent>
          </Card>
          <div className="space-y-3">
            <h2 className="font-medium">My correction requests</h2>
            {corrections.isPending ? (
              <Skeleton className="h-32" />
            ) : (corrections.data?.data.length ?? 0) === 0 ? (
              <EmptyState
                icon={ClipboardList}
                title="No requests yet"
                description="If a day looks wrong, click it in the calendar and request a correction."
              />
            ) : (
              corrections.data?.data.map((correction) => (
                <CorrectionCard key={correction.id} correction={correction} timezone={timezone} showEmployee={false} />
              ))
            )}
          </div>
        </div>
      </div>
      <AttendanceDayDialog day={selected} onOpenChange={(open) => !open && setSelected(null)} />
    </>
  );
}
