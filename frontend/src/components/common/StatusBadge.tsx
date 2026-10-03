import { cn } from "@/lib/utils";
import type { Tone } from "@/lib/labels";

const toneClasses: Record<Tone, string> = {
  ok: "bg-status-ok/12 text-status-ok ring-status-ok/30",
  warn: "bg-status-warn/15 text-status-warn ring-status-warn/35",
  bad: "bg-status-bad/12 text-status-bad ring-status-bad/30",
  info: "bg-status-info/12 text-status-info ring-status-info/30",
  neutral: "bg-status-neutral/12 text-status-neutral ring-status-neutral/30",
  leave: "bg-status-leave/12 text-status-leave ring-status-leave/30",
};

const dotClasses: Record<Tone, string> = {
  ok: "bg-status-ok",
  warn: "bg-status-warn",
  bad: "bg-status-bad",
  info: "bg-status-info",
  neutral: "bg-status-neutral",
  leave: "bg-status-leave",
};

/** Status is always colour plus text, never colour alone (requirements §13). */
export function StatusBadge({ label, tone, className }: { label: string; tone: Tone; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset",
        toneClasses[tone],
        className,
      )}
    >
      <span aria-hidden className={cn("size-1.5 rounded-full", dotClasses[tone])} />
      {label}
    </span>
  );
}
