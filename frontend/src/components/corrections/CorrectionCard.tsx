import { ArrowRight } from "lucide-react";

import type { CorrectionOut } from "@/api/generated/model";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCorrectionValue } from "@/lib/correctionValue";
import { formatDate, formatDateTime } from "@/lib/format";
import { correctionFieldLabel, correctionStatusLabel } from "@/lib/labels";
import type { ReactNode } from "react";

/** Old and new value side by side (§13 screen 11). */
export function CorrectionCard({
  correction,
  timezone,
  actions,
  showEmployee = true,
}: {
  correction: CorrectionOut;
  timezone: string;
  actions?: ReactNode;
  showEmployee?: boolean;
}) {
  const status = correctionStatusLabel[correction.status];
  return (
    <Card className="gap-3">
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2">
        <div>
          <CardTitle className="text-base">
            {showEmployee ? `${correction.employee_name} · ` : ""}
            {formatDate(correction.work_date)}
          </CardTitle>
          <p className="text-muted-foreground text-xs">
            {correctionFieldLabel[correction.field]} · requested by {correction.requested_by_name ?? "—"} on{" "}
            {formatDateTime(correction.created_at, timezone)}
          </p>
        </div>
        <StatusBadge label={status.label} tone={status.tone} />
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 rounded-md border p-3 text-sm">
          <div>
            <p className="text-muted-foreground text-xs">Current</p>
            <p className="font-medium">{formatCorrectionValue(correction.field, correction.old_value, timezone)}</p>
          </div>
          <ArrowRight className="text-muted-foreground size-4" aria-label="changes to" />
          <div>
            <p className="text-muted-foreground text-xs">Requested</p>
            <p className="font-medium">{formatCorrectionValue(correction.field, correction.new_value, timezone)}</p>
          </div>
        </div>
        <p className="text-sm">
          <span className="text-muted-foreground">Reason: </span>
          {correction.reason}
        </p>
        {correction.status !== "pending" && (
          <p className="text-muted-foreground text-xs">
            {correction.status === "approved" ? "Approved" : "Rejected"} by {correction.approved_by_name ?? "—"}
            {correction.approved_at && ` on ${formatDateTime(correction.approved_at, timezone)}`}
            {correction.review_comment && ` — “${correction.review_comment}”`}
          </p>
        )}
        {actions}
      </CardContent>
    </Card>
  );
}
