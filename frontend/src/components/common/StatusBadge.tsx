import { cn } from "@/lib/utils";
import type { Tone } from "@/lib/labels";

// A 10% tint keeps the label text >= 4.5:1 against its own badge in the light theme (WCAG AA).
const toneClasses: Record<Tone, string> = {
  ok: "bg-status-ok/10 text-status-ok ring-status-ok/25",
  warn: "bg-status-warn/10 text-status-warn ring-status-warn/25",
  bad: "bg-status-bad/10 text-status-bad ring-status-bad/25",
  info: "bg-status-info/10 text-status-info ring-status-info/25",
  neutral: "bg-status-neutral/10 text-status-neutral ring-status-neutral/25",
  leave: "bg-status-leave/10 text-status-leave ring-status-leave/25",
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
