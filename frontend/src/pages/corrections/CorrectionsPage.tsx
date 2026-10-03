import { Check, ClipboardList, X } from "lucide-react";
import { useState } from "react";

import type { CorrectionOut, CorrectionStatus } from "@/api/generated/model";
import { CorrectionCard } from "@/components/corrections/CorrectionCard";
import { DecisionDialog } from "@/components/corrections/DecisionDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCorrections } from "@/hooks/useAttendance";
import { useTimezone } from "@/hooks/useAuth";
import { useUrlState } from "@/hooks/useUrlState";

const PAGE_SIZE = 20;

/** §13 screen 11: pending / approved / rejected; approve or reject with a comment (ADR-0004). */
export function CorrectionsPage() {
  const timezone = useTimezone();
  const url = useUrlState();
  const status = (url.get("status") ?? "pending") as CorrectionStatus;
  const query = useCorrections({ status, page: url.page, page_size: PAGE_SIZE, sort: status === "pending" ? "created_at" : "-created_at" });
  const [decision, setDecision] = useState<{ correction: CorrectionOut; approve: boolean } | null>(null);
  const total = query.data?.pagination.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <>
      <PageHeader title="Corrections" description="Requests from employees, and corrections already applied." />
      <Tabs value={status} onValueChange={(value) => url.set({ status: value })} className="mb-4">
        <TabsList>
          <TabsTrigger value="pending">Pending</TabsTrigger>
          <TabsTrigger value="approved">Approved</TabsTrigger>
          <TabsTrigger value="rejected">Rejected</TabsTrigger>
        </TabsList>
      </Tabs>
      {query.isPending ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : query.data.data.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          title={status === "pending" ? "No requests waiting" : `No ${status} corrections`}
          description={
            status === "pending"
              ? "Employees request corrections from My attendance; they appear here for you to decide."
              : "Corrections you or others decided appear here."
          }
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {query.data.data.map((correction) => (
            <CorrectionCard
              key={correction.id}
              correction={correction}
              timezone={timezone}
              actions={
                correction.status === "pending" && (
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => setDecision({ correction, approve: true })}>
                      <Check aria-hidden /> Approve
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setDecision({ correction, approve: false })}>
                      <X aria-hidden /> Reject
                    </Button>
                  </div>
                )
              }
            />
          ))}
        </div>
      )}
      {pages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-2 text-sm">
          <Button variant="outline" size="sm" disabled={url.page <= 1} onClick={() => url.set({ page: url.page - 1 })}>
            Previous
          </Button>
          <span className="tabular-nums">
            {url.page} / {pages}
          </span>
          <Button variant="outline" size="sm" disabled={url.page >= pages} onClick={() => url.set({ page: url.page + 1 })}>
            Next
          </Button>
        </div>
      )}
      <DecisionDialog decision={decision} onClose={() => setDecision(null)} />
    </>
  );
}
