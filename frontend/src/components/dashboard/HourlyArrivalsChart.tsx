import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { HourlyCount } from "@/api/generated/model";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function HourlyArrivalsChart({ data }: { data: HourlyCount[] }) {
  const rows = data.map((d) => ({ hour: `${String(d.hour).padStart(2, "0")}:00`, count: d.count }));
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Arrivals by hour</CardTitle>
      </CardHeader>
      <CardContent className="h-64">
        {rows.every((r) => r.count === 0) ? (
          <p className="text-muted-foreground flex h-full items-center justify-center text-sm">No check-ins yet today.</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis dataKey="hour" tickLine={false} axisLine={false} fontSize={12} stroke="var(--muted-foreground)" />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} fontSize={12} stroke="var(--muted-foreground)" />
              <Tooltip
                cursor={{ fill: "var(--muted)" }}
                contentStyle={{ background: "var(--popover)", color: "var(--popover-foreground)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 13 }}
              />
              <Bar dataKey="count" name="Check-ins" fill="var(--chart-1)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
