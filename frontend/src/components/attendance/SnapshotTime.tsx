import { mediaUrl } from "@/api/media";
import { SecureImage } from "@/components/common/SecureImage";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatTime } from "@/lib/format";

/** A check-in/out time; hovering shows the face snapshot of the event behind it (§13 screen 7). */
export function SnapshotTime({
  time,
  eventId,
  timezone,
  name,
}: {
  time: string | null;
  eventId: number | null;
  timezone: string;
  name: string;
}) {
  const text = formatTime(time, timezone);
  if (!time || !eventId) return <span className="tabular-nums">{text}</span>;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" className="tabular-nums underline decoration-dotted underline-offset-4">
          {text}
        </button>
      </TooltipTrigger>
      <TooltipContent side="right" className="bg-popover text-popover-foreground border p-1">
        <SecureImage src={mediaUrl.eventSnapshot(eventId)} alt={`Snapshot of ${name}`} fallbackName={name} className="size-32 rounded" />
      </TooltipContent>
    </Tooltip>
  );
}
