import { CalendarOff, Clock, DoorOpen, ScanFace, UserCheck, UserX, type LucideIcon } from "lucide-react";

import type { DashboardSummary } from "@/api/generated/model";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface Kpi {
  label: string;
  value: number;
  icon: LucideIcon;
  tone: string;
  hint?: string;
}

/** §13 screen 2: Present, Late, Absent, On Leave, In office now, Unknown today (values from the API). */
export function KpiCards({ summary }: { summary: DashboardSummary | undefined }) {
  if (!summary) {
    return (
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
    );
  }
  const kpis: Kpi[] = [
    { label: "Present", value: summary.present, icon: UserCheck, tone: "text-status-ok", hint: `of ${summary.expected} expected` },
    { label: "Late", value: summary.late, icon: Clock, tone: "text-status-warn" },
    { label: "Absent", value: summary.absent, icon: UserX, tone: "text-status-bad" },
    { label: "On leave", value: summary.on_leave, icon: CalendarOff, tone: "text-status-leave" },
    { label: "In office now", value: summary.in_office_now, icon: DoorOpen, tone: "text-status-info" },
    { label: "Unknown today", value: summary.unknown_today, icon: ScanFace, tone: "text-status-warn" },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      {kpis.map(({ label, value, icon: Icon, tone, hint }) => (
        <Card key={label} className="gap-2 py-4">
          <CardContent className="px-4">
            <div className="text-muted-foreground flex items-center justify-between text-sm font-medium">
              {label}
              <Icon className={cn("size-4", tone)} aria-hidden />
            </div>
            <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
            {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
