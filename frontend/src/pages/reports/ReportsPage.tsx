import { FileText, Play } from "lucide-react";
import { useMemo } from "react";

import type { AttendanceStatus, ReportType } from "@/api/generated/model";
import { EmployeeCombobox } from "@/components/common/EmployeeCombobox";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { FilterSelect } from "@/components/common/FilterSelect";
import { PageHeader } from "@/components/common/PageHeader";
import { ExportButtons } from "@/components/reports/ExportButtons";
import { ReportOverview } from "@/components/reports/ReportOverview";
import { ReportTable } from "@/components/reports/ReportTable";
import { ScheduleDialog } from "@/components/reports/ScheduleDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/hooks/useAuth";
import { useDepartments } from "@/hooks/useOrganization";
import { useReport, type ReportFilters } from "@/hooks/useReports";
import { useUrlState } from "@/hooks/useUrlState";
import { todayIn } from "@/lib/format";
import { attendanceStatusLabel } from "@/lib/labels";
import { Permission } from "@/lib/permissions";
import { REPORTS, reportInfo } from "@/lib/reports";

/** §13 screen 12 (FR-30, FR-31, FR-32). Filters live in the URL; `run=1` shows the preview. */
export function ReportsPage() {
  const { can, timezone } = useAuth();
  const url = useUrlState();
  const departments = useDepartments();
  const today = todayIn(timezone);
  const type = (url.get("type") ?? "daily") as ReportType;
  const info = reportInfo(type);
  const filters: ReportFilters = {
    date_from: url.get("from") ?? `${today.slice(0, 8)}01`,
    date_to: url.get("to") ?? today,
    department_id: url.getNumber("department_id") ?? undefined,
    employee_id: url.getNumber("employee_id") ?? undefined,
    status: info.statusFilter ? ((url.get("status") as AttendanceStatus | null) ?? undefined) : undefined,
  };
  const needsEmployee = type === "employee_history" && !filters.employee_id;
  const ran = url.get("run") === "1" && !needsEmployee;
  const filtersKey = JSON.stringify(filters);
  // Stable object per filter combination, so the query key does not change on every render.
  const params = useMemo<ReportFilters | null>(() => (ran ? (JSON.parse(filtersKey) as ReportFilters) : null), [ran, filtersKey]);
  const report = useReport(type, params);
  const employeeLabel = url.get("employee_label");

  return (
    <>
      <PageHeader
        title="Reports"
        description="Preview a report, then export it to Excel or PDF."
        actions={can(Permission.settingsManage) && <ScheduleDialog defaultType={type} />}
      />
      <Card className="mb-4">
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="space-y-1.5 xl:col-span-2">
            <Label htmlFor="report-type">Report</Label>
            <Select value={type} onValueChange={(value) => url.set({ type: value, run: null })}>
              <SelectTrigger id="report-type" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {REPORTS.map((r) => (
                  <SelectItem key={r.type} value={r.type}>
                    {r.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-muted-foreground text-xs">{info.description}</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="report-from">From</Label>
            <Input id="report-from" type="date" max={today} value={filters.date_from} onChange={(e) => url.set({ from: e.target.value, run: null })} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="report-to">To</Label>
            <Input id="report-to" type="date" max={today} value={filters.date_to} onChange={(e) => url.set({ to: e.target.value, run: null })} />
          </div>
          <div className="space-y-1.5">
            <Label>Department</Label>
            <FilterSelect
              label="Department"
              allLabel="All departments"
              className="w-full"
              value={url.get("department_id")}
              options={(departments.data?.data ?? []).map((d) => ({ value: String(d.id), label: d.name }))}
              onChange={(department_id) => url.set({ department_id, run: null })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="report-employee">Employee{type === "employee_history" ? " (required)" : ""}</Label>
            <EmployeeCombobox
              id="report-employee"
              placeholder="All employees"
              value={filters.employee_id ? { id: filters.employee_id, label: employeeLabel ?? `#${filters.employee_id}` } : null}
              onChange={(option) => url.set({ employee_id: option?.id ?? null, employee_label: option?.label ?? null, run: null })}
            />
          </div>
          {info.statusFilter && (
            <div className="space-y-1.5">
              <Label>Status</Label>
              <FilterSelect
                label="Status"
                allLabel="Any status"
                className="w-full"
                value={url.get("status")}
                options={(Object.keys(attendanceStatusLabel) as AttendanceStatus[]).map((s) => ({
                  value: s,
                  label: attendanceStatusLabel[s].label,
                }))}
                onChange={(status) => url.set({ status, run: null })}
              />
            </div>
          )}
          <div className="flex items-end gap-2 xl:col-span-4">
            <Button onClick={() => url.set({ run: 1 })} disabled={needsEmployee}>
              <Play aria-hidden /> Run report
            </Button>
            {ran && <ExportButtons reportType={type} params={filters} />}
            {needsEmployee && <span className="text-muted-foreground text-sm">Choose the employee first.</span>}
          </div>
        </CardContent>
      </Card>

      {!ran ? (
        <EmptyState icon={FileText} title="Choose a report and filters" description="Then select Run report to preview it here." />
      ) : report.isPending ? (
        <div className="space-y-4">
          <Skeleton className="h-40" />
          <Skeleton className="h-64" />
        </div>
      ) : report.isError ? (
        <ErrorState error={report.error} onRetry={() => void report.refetch()} />
      ) : (
        <div className="space-y-4">
          <ReportOverview report={report.data} />
          {report.data.truncated && (
            <p className="text-muted-foreground text-sm" role="status">
              Showing the first {report.data.rows.length} of {report.data.total_rows} rows. Export to Excel for every row.
            </p>
          )}
          <ReportTable report={report.data} />
        </div>
      )}
    </>
  );
}
