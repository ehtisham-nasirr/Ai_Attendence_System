import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { ReportOut } from "@/api/generated/model";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatMinutes } from "@/lib/format";

const COLORS = ["var(--chart-1)", "var(--chart-3)", "var(--chart-4)", "var(--chart-2)", "var(--chart-5)"];

export function ReportOverview({ report }: { report: ReportOut }) {
  const chart = report.chart;
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="grid grid-cols-2 gap-3 self-start">
        {report.summary.map((item) => (
          <Card key={item.label} className="gap-1 py-3">
            <CardContent className="px-4">
              <p className="text-muted-foreground text-sm">{item.label}</p>
              <p className="text-xl font-semibold tabular-nums">
                {item.kind === "minutes" ? formatMinutes(Number(item.value)) : String(item.value)}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
      {chart && chart.data.length > 0 && (
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">{report.title}</CardTitle>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chart.data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--border)" />
                <XAxis dataKey={chart.x_key} tickLine={false} axisLine={false} fontSize={12} stroke="var(--muted-foreground)" />
                <YAxis allowDecimals={false} tickLine={false} axisLine={false} fontSize={12} stroke="var(--muted-foreground)" />
                <Tooltip
                  cursor={{ fill: "var(--muted)" }}
                  contentStyle={{ background: "var(--popover)", color: "var(--popover-foreground)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 13 }}
                />
                {chart.series.length > 1 && <Legend wrapperStyle={{ fontSize: 13 }} />}
                {chart.series.map((series, index) => (
                  <Bar
                    key={series.key}
                    dataKey={series.key}
                    name={series.label}
                    fill={COLORS[index % COLORS.length]}
                    isAnimationActive={false}
                    radius={[3, 3, 0, 0]}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
