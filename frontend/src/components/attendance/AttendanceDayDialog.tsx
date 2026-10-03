import type { AttendanceDayOut } from "@/api/generated/model";
import { mediaUrl } from "@/api/media";
import { CorrectionForm } from "@/components/attendance/CorrectionForm";
import { SecureImage } from "@/components/common/SecureImage";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { useAuth } from "@/hooks/useAuth";
import { formatDate, formatMinutes, formatTime } from "@/lib/format";
import { attendanceStatusLabel } from "@/lib/labels";
import { Permission } from "@/lib/permissions";

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="text-sm font-medium">{value}</dd>
    </div>
  );
}

/** One employee-day: the computed values, snapshots, and the correction form. */
export function AttendanceDayDialog({
  day,
  onOpenChange,
}: {
  day: AttendanceDayOut | null;
  onOpenChange: (open: boolean) => void;
}) {
  const { can, timezone } = useAuth();
  const canApply = can(Permission.attendanceCorrect);
  const canRequest = can(Permission.correctionsRequest);
  const status = day?.status ? attendanceStatusLabel[day.status] : null;
  return (
    <Dialog open={day !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        {day && (
          <>
            <DialogHeader>
              <DialogTitle>
                {day.employee_name} · {formatDate(day.work_date)}
              </DialogTitle>
              <DialogDescription>
                {day.shift_name ?? "No shift"}
                {day.is_manual && " · includes a manual correction"}
                {!day.finalized_at && " · provisional until the day closes"}
              </DialogDescription>
            </DialogHeader>
            <div className="flex items-center gap-2">
              {status ? <StatusBadge label={status.label} tone={status.tone} /> : <span className="text-sm">No status yet</span>}
            </div>
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Detail label="Check-in" value={formatTime(day.check_in_at, timezone)} />
              <Detail label="Check-out" value={formatTime(day.check_out_at, timezone)} />
              <Detail label="Worked" value={formatMinutes(day.worked_minutes)} />
              <Detail label="Late" value={formatMinutes(day.late_minutes)} />
              <Detail label="Early exit" value={formatMinutes(day.early_minutes)} />
              <Detail label="Overtime" value={formatMinutes(day.overtime_minutes)} />
            </dl>
            {(day.check_in_event_id || day.check_out_event_id) && canApply && (
              <div className="flex gap-3">
                {day.check_in_event_id && (
                  <figure className="space-y-1">
                    <SecureImage
                      src={mediaUrl.eventSnapshot(day.check_in_event_id)}
                      alt="Check-in snapshot"
                      fallbackName={day.employee_name}
                      className="size-24 rounded-md"
                    />
                    <figcaption className="text-muted-foreground text-xs">Check-in</figcaption>
                  </figure>
                )}
                {day.check_out_event_id && (
                  <figure className="space-y-1">
                    <SecureImage
                      src={mediaUrl.eventSnapshot(day.check_out_event_id)}
                      alt="Check-out snapshot"
                      fallbackName={day.employee_name}
                      className="size-24 rounded-md"
                    />
                    <figcaption className="text-muted-foreground text-xs">Check-out</figcaption>
                  </figure>
                )}
              </div>
            )}
            {(canApply || canRequest) && (
              <>
                <Separator />
                <div className="space-y-3">
                  <h3 className="font-medium">{canApply ? "Correct this day" : "Request a correction"}</h3>
                  <CorrectionForm key={day.id} day={day} appliesDirectly={canApply} onDone={() => onOpenChange(false)} />
                </div>
              </>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
