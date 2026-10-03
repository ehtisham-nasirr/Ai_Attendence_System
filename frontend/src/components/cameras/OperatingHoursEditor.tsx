import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { OperatingWindow } from "@/lib/schemas/camera";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Time windows when the camera is processed; outside them it is PAUSED (§10.4). */
export function OperatingHoursEditor({
  value,
  onChange,
}: {
  value: OperatingWindow[];
  onChange: (windows: OperatingWindow[]) => void;
}) {
  const update = (index: number, patch: Partial<OperatingWindow>) =>
    onChange(value.map((window, i) => (i === index ? { ...window, ...patch } : window)));
  return (
    <div className="space-y-3">
      {value.map((window, index) => (
        <div key={index} className="flex flex-wrap items-center gap-2 rounded-md border p-2">
          <ToggleGroup
            type="multiple"
            size="sm"
            variant="outline"
            aria-label="Days"
            value={window.days.map(String)}
            onValueChange={(days) => update(index, { days: days.map(Number).sort() })}
          >
            {DAYS.map((label, i) => (
              <ToggleGroupItem key={label} value={String(i + 1)} aria-label={label}>
                {label.slice(0, 2)}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <Input type="time" aria-label="From" className="w-28" value={window.start} onChange={(e) => update(index, { start: e.target.value })} />
          <span className="text-muted-foreground text-sm">to</span>
          <Input type="time" aria-label="To" className="w-28" value={window.end} onChange={(e) => update(index, { end: e.target.value })} />
          <Button type="button" variant="ghost" size="icon" aria-label="Remove window" onClick={() => onChange(value.filter((_, i) => i !== index))}>
            <Trash2 />
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onChange([...value, { days: [1, 2, 3, 4, 5], start: "07:00", end: "21:00" }])}
      >
        <Plus aria-hidden /> Add time window
      </Button>
    </div>
  );
}
