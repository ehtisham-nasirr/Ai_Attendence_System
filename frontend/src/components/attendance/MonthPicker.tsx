import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { monthLabel, shiftMonth } from "@/lib/month";

export function MonthPicker({ month, onChange, max }: { month: string; onChange: (month: string) => void; max?: string }) {
  return (
    <div className="flex items-center gap-1">
      <Button variant="outline" size="icon" className="size-8" aria-label="Previous month" onClick={() => onChange(shiftMonth(month, -1))}>
        <ChevronLeft />
      </Button>
      <span className="min-w-36 text-center text-sm font-medium" aria-live="polite">
        {monthLabel(month)}
      </span>
      <Button
        variant="outline"
        size="icon"
        className="size-8"
        aria-label="Next month"
        disabled={max !== undefined && month >= max}
        onClick={() => onChange(shiftMonth(month, 1))}
      >
        <ChevronRight />
      </Button>
    </div>
  );
}
