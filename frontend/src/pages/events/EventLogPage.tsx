import type { ColumnDef } from "@tanstack/react-table";
import { Ban, ListChecks } from "lucide-react";
import { useMemo, useState } from "react";

import type { EventOut, ListEventsParams, RecognitionStatus } from "@/api/generated/model";
import { mediaUrl } from "@/api/media";
import { DataTable } from "@/components/common/DataTable";
import { EmptyState } from "@/components/common/EmptyState";
import { FilterSelect } from "@/components/common/FilterSelect";
import { PageHeader } from "@/components/common/PageHeader";
import { SecureImage } from "@/components/common/SecureImage";
import { StatusBadge } from "@/components/common/StatusBadge";
import { VoidDialog } from "@/components/events/VoidDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useTimezone } from "@/hooks/useAuth";
import { useCameras } from "@/hooks/useCameras";
import { exportEvents, useEvents } from "@/hooks/useRecognition";
import { useUrlState } from "@/hooks/useUrlState";
import { formatDateTime, formatPercent, localToUtcIso, todayIn } from "@/lib/format";
import { recognitionStatusLabel } from "@/lib/labels";
import { nextDay } from "@/lib/month";

/** §13 screen 10: every recognition event; void false recognitions with a reason (FR-28). */
export function EventLogPage() {
  const timezone = useTimezone();
  const url = useUrlState();
  const cameras = useCameras({ page: 1, page_size: 200 }, false);
  const [voiding, setVoiding] = useState<EventOut | null>(null);
  const day = url.get("date") ?? todayIn(timezone);
  const filters: ListEventsParams = {
    camera_id: url.getNumber("camera_id") ?? undefined,
    status: (url.get("status") as RecognitionStatus | null) ?? undefined,
    // The selected local day, as UTC instants.
    date_from: localToUtcIso(day, "00:00", timezone),
    date_to: localToUtcIso(nextDay(day), "00:00", timezone),
    sort: url.sort ?? undefined,
  };
  const query = useEvents({ ...filters, page: url.page, page_size: url.pageSize });

  const columns = useMemo<ColumnDef<EventOut>[]>(
    () => [
      {
        id: "snapshot",
        header: "",
        meta: { className: "w-14" },
        cell: ({ row }) => (
          <SecureImage
            src={row.original.snapshot_available ? mediaUrl.eventSnapshot(row.original.id) : null}
            alt="Event snapshot"
            fallbackName={row.original.employee_name}
            className="size-10 rounded-md"
          />
        ),
      },
      {
        id: "time",
        header: "Time",
        meta: { sortKey: "captured_at", exportValue: (e) => formatDateTime(e.captured_at, timezone) },
        cell: ({ row }) => <span className="tabular-nums">{formatDateTime(row.original.captured_at, timezone)}</span>,
      },
      {
        id: "employee",
        header: "Employee",
        meta: { exportValue: (e) => (e.employee_code ? `${e.employee_code} ${e.employee_name ?? ""}` : "Unknown") },
        cell: ({ row }) =>
          row.original.employee_name ? (
            <div>
              <p className="font-medium">{row.original.employee_name}</p>
              <p className="text-muted-foreground text-xs tabular-nums">{row.original.employee_code}</p>
            </div>
          ) : (
            <span className="text-muted-foreground">Unknown</span>
          ),
      },
      {
        id: "camera",
        header: "Camera",
        meta: { exportValue: (e) => e.camera_name ?? e.camera_id },
        cell: ({ row }) => row.original.camera_name ?? `Camera ${row.original.camera_id}`,
      },
      {
        id: "confidence",
        header: "Confidence",
        meta: { sortKey: "confidence", exportValue: (e) => e.confidence },
        cell: ({ row }) => <span className="tabular-nums">{formatPercent(row.original.confidence)}</span>,
      },
      {
        id: "status",
        header: "Status",
        meta: { exportValue: (e) => e.status },
        cell: ({ row }) => {
          const status = recognitionStatusLabel[row.original.status];
          return (
            <div>
              <StatusBadge label={status.label} tone={status.tone} />
              {row.original.void_reason && <p className="text-muted-foreground mt-1 text-xs">{row.original.void_reason}</p>}
            </div>
          );
        },
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) =>
          row.original.status === "recognized" ? (
            <Button variant="ghost" size="sm" onClick={() => setVoiding(row.original)}>
              <Ban aria-hidden /> Void
            </Button>
          ) : null,
      },
    ],
    [timezone],
  );

  return (
    <>
      <PageHeader title="Event log" description="All recognition events. Void a recognition that picked the wrong person." />
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
        exportAll={() => exportEvents(filters)}
        exportFileName={`events-${day}.csv`}
        toolbar={
          <>
            <Input
              type="date"
              aria-label="Date"
              className="w-full sm:w-44"
              value={day}
              max={todayIn(timezone)}
              onChange={(event) => url.set({ date: event.target.value || null })}
            />
            <FilterSelect
              label="Camera"
              allLabel="All cameras"
              value={url.get("camera_id")}
              options={(cameras.data?.data ?? []).map((c) => ({ value: String(c.id), label: c.name }))}
              onChange={(camera_id) => url.set({ camera_id })}
            />
            <FilterSelect
              label="Status"
              allLabel="Any status"
              value={url.get("status")}
              options={(Object.keys(recognitionStatusLabel) as RecognitionStatus[]).map((s) => ({
                value: s,
                label: recognitionStatusLabel[s].label,
              }))}
              onChange={(status) => url.set({ status })}
            />
          </>
        }
        empty={<EmptyState icon={ListChecks} title="No events on this day" description="Pick another date or camera." />}
      />
      <VoidDialog event={voiding} onClose={() => setVoiding(null)} />
    </>
  );
}
