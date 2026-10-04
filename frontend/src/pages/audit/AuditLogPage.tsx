import type { ColumnDef } from "@tanstack/react-table";
import { ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";

import type { AuditLogOut, ListAuditLogsParams } from "@/api/generated/model";
import { DataTable } from "@/components/common/DataTable";
import { EmptyState } from "@/components/common/EmptyState";
import { PageHeader } from "@/components/common/PageHeader";
import { SearchInput } from "@/components/common/SearchInput";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { exportAuditLogs, useAuditLogs } from "@/hooks/useAuditLogs";
import { useTimezone } from "@/hooks/useAuth";
import { useUrlState } from "@/hooks/useUrlState";
import { formatDateTime, localToUtcIso } from "@/lib/format";
import { nextDay } from "@/lib/month";

function Values({ title, values }: { title: string; values: unknown }) {
  return (
    <div className="min-w-0">
      <p className="text-muted-foreground mb-1 text-xs font-medium">{title}</p>
      <pre className="bg-muted max-h-72 overflow-auto rounded-md p-2 text-xs whitespace-pre-wrap">
        {values === null || values === undefined ? "—" : JSON.stringify(values, null, 2)}
      </pre>
    </div>
  );
}

/** §13 screen 14 (Admin), FR-37: who changed what, with old and new values. */
export function AuditLogPage() {
  const timezone = useTimezone();
  const url = useUrlState();
  const [selected, setSelected] = useState<AuditLogOut | null>(null);
  const from = url.get("from");
  const to = url.get("to");
  const filters: ListAuditLogsParams = {
    action: url.get("action") || undefined,
    entity: url.get("entity") || undefined,
    date_from: from ? localToUtcIso(from, "00:00", timezone) : undefined,
    date_to: to ? localToUtcIso(nextDay(to), "00:00", timezone) : undefined,
    sort: url.sort ?? undefined,
  };
  const query = useAuditLogs({ ...filters, page: url.page, page_size: url.pageSize });

  const columns = useMemo<ColumnDef<AuditLogOut>[]>(
    () => [
      {
        id: "time",
        header: "Time",
        meta: { sortKey: "created_at", exportValue: (a) => a.created_at },
        cell: ({ row }) => <span className="tabular-nums">{formatDateTime(row.original.created_at, timezone)}</span>,
      },
      {
        id: "user",
        header: "User",
        meta: { exportValue: (a) => a.user_name ?? a.user_id ?? "system" },
        cell: ({ row }) => row.original.user_name ?? (row.original.user_id ? `User ${row.original.user_id}` : "System"),
      },
      { id: "action", header: "Action", meta: { exportValue: (a) => a.action }, cell: ({ row }) => <span className="font-mono text-xs">{row.original.action}</span> },
      {
        id: "entity",
        header: "Record",
        meta: { exportValue: (a) => `${a.entity}${a.entity_id ? ` #${a.entity_id}` : ""}` },
        cell: ({ row }) => `${row.original.entity}${row.original.entity_id ? ` #${row.original.entity_id}` : ""}`,
      },
      { id: "ip", header: "IP", meta: { exportValue: (a) => a.ip ?? "" }, cell: ({ row }) => row.original.ip ?? "—" },
      {
        id: "details",
        header: "",
        cell: ({ row }) => (
          <Button variant="ghost" size="sm" onClick={() => setSelected(row.original)}>
            Details
          </Button>
        ),
      },
    ],
    [timezone],
  );

  return (
    <>
      <PageHeader title="Audit log" description="Every change, login, export and correction, with old and new values." />
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
        exportAll={() => exportAuditLogs(filters)}
        exportFileName="audit-log.csv"
        exportTitle="Audit log"
        toolbar={
          <>
            <SearchInput value={url.get("action") ?? ""} onChange={(action) => url.set({ action })} placeholder="Action, e.g. employee.update" />
            <SearchInput value={url.get("entity") ?? ""} onChange={(entity) => url.set({ entity })} placeholder="Record type, e.g. camera" />
            <Input type="date" aria-label="From" className="w-full sm:w-40" value={from ?? ""} onChange={(e) => url.set({ from: e.target.value })} />
            <Input type="date" aria-label="To" className="w-full sm:w-40" value={to ?? ""} onChange={(e) => url.set({ to: e.target.value })} />
          </>
        }
        empty={<EmptyState icon={ShieldCheck} title="No audit entries match" description="Widen the date range or clear the filters." />}
      />
      <Dialog open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="sm:max-w-3xl">
          {selected && (
            <>
              <DialogHeader>
                <DialogTitle className="font-mono text-base">{selected.action}</DialogTitle>
                <DialogDescription>
                  {selected.user_name ?? "System"} · {formatDateTime(selected.created_at, timezone)} · {selected.ip ?? "no IP"}
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-3 md:grid-cols-2">
                <Values title="Before" values={selected.old_values} />
                <Values title="After" values={selected.new_values} />
              </div>
              {selected.user_agent && <p className="text-muted-foreground truncate text-xs">{selected.user_agent}</p>}
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
