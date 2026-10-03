import { useLiveFeed } from "@/hooks/useLiveFeed";
import { cn } from "@/lib/utils";

const labels = { open: "Live", connecting: "Connecting…", closed: "Reconnecting…", paused: "Paused" } as const;

export function LiveIndicator() {
  const { status } = useLiveFeed();
  return (
    <span className="text-muted-foreground hidden items-center gap-1.5 text-xs sm:inline-flex" role="status">
      <span
        aria-hidden
        className={cn(
          "size-2 rounded-full",
          status === "open" ? "bg-status-ok" : status === "paused" ? "bg-status-neutral" : "bg-status-warn",
        )}
      />
      {labels[status]}
    </span>
  );
}
