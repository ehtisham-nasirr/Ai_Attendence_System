import { Radio } from "lucide-react";

import { mediaUrl } from "@/api/media";
import { EmptyState } from "@/components/common/EmptyState";
import { SecureImage } from "@/components/common/SecureImage";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useTimezone } from "@/hooks/useAuth";
import { formatTime, formatPercent } from "@/lib/format";
import { recognitionStatusLabel } from "@/lib/labels";
import type { RecognitionCreatedData } from "@/lib/live";

/** Newest recognitions as they arrive over /ws/live (§13 screen 2). */
export function LiveEventFeed({
  events,
  cameraNames,
  showSnapshots,
}: {
  events: RecognitionCreatedData[];
  cameraNames: Map<number, string>;
  showSnapshots: boolean;
}) {
  const timezone = useTimezone();
  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <CardTitle className="text-base">Live events</CardTitle>
      </CardHeader>
      <CardContent className="flex-1 px-0">
        {events.length === 0 ? (
          <EmptyState icon={Radio} title="Waiting for recognitions" description="New check-ins appear here as they happen." />
        ) : (
          <ScrollArea className="h-80 px-4">
            <ul className="divide-y" aria-live="polite">
              {events.map((event) => {
                const status = recognitionStatusLabel[event.status];
                return (
                  <li key={event.event_id} className="flex items-center gap-3 py-2">
                    <SecureImage
                      src={showSnapshots && event.snapshot_available ? mediaUrl.eventSnapshot(event.event_id) : null}
                      alt={event.employee_name ? `Snapshot of ${event.employee_name}` : "Unknown face snapshot"}
                      fallbackName={event.employee_name}
                      className="size-10 shrink-0 rounded-md"
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{event.employee_name ?? "Unknown person"}</p>
                      <p className="text-muted-foreground truncate text-xs">
                        {cameraNames.get(event.camera_id) ?? `Camera ${event.camera_id}`} ·{" "}
                        {formatTime(event.captured_at, timezone)}
                        {event.status === "recognized" && ` · ${formatPercent(event.confidence)}`}
                      </p>
                    </div>
                    <StatusBadge label={status.label} tone={status.tone} />
                  </li>
                );
              })}
            </ul>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
