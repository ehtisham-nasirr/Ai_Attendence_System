import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { listCameras, listEvents } from "@/api/generated/endpoints";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { CameraHealthStrip } from "@/components/dashboard/CameraHealthStrip";
import { DepartmentAttendanceChart } from "@/components/dashboard/DepartmentAttendanceChart";
import { HourlyArrivalsChart } from "@/components/dashboard/HourlyArrivalsChart";
import { KpiCards } from "@/components/dashboard/KpiCards";
import { LiveEventFeed } from "@/components/dashboard/LiveEventFeed";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/hooks/useAuth";
import { useDashboard } from "@/hooks/useDashboard";
import { useLiveLoadLevels, useRecentEvents } from "@/hooks/useLiveFeed";
import { useLocationFilter } from "@/hooks/useLocationFilter";
import { formatDate } from "@/lib/format";
import { Permission } from "@/lib/permissions";
import type { RecognitionCreatedData } from "@/lib/live";

export function DashboardPage() {
  const { can } = useAuth();
  const { locationId } = useLocationFilter();
  const dashboard = useDashboard(locationId);
  const liveEvents = useRecentEvents();
  const liveLoad = useLiveLoadLevels();
  const canSeeEvents = can(Permission.eventsView);

  // Seed the feed with the latest events so it is not empty right after opening the page.
  const recent = useQuery({
    queryKey: ["events", { page_size: 15, sort: "-captured_at" }],
    queryFn: () => listEvents({ page: 1, page_size: 15, sort: "-captured_at" }),
    enabled: canSeeEvents,
  });
  const cameras = useQuery({
    queryKey: ["cameras", "names"],
    queryFn: () => listCameras({ page: 1, page_size: 200 }),
    enabled: can(Permission.camerasManage) || can(Permission.liveView),
    staleTime: 5 * 60_000,
  });

  const feed = useMemo<RecognitionCreatedData[]>(() => {
    const seeded: RecognitionCreatedData[] = (recent.data?.data ?? []).map((event) => ({
      event_id: event.id,
      camera_id: event.camera_id,
      status: event.status,
      employee_id: event.employee_id,
      employee_code: event.employee_code ?? null,
      employee_name: event.employee_name ?? null,
      department_id: null,
      confidence: event.confidence,
      captured_at: event.captured_at,
      bbox: null,
      snapshot_available: event.snapshot_available,
    }));
    const seen = new Set(liveEvents.map((e) => e.event_id));
    return [...liveEvents, ...seeded.filter((e) => !seen.has(e.event_id))].slice(0, 50);
  }, [liveEvents, recent.data]);

  const cameraNames = useMemo(() => {
    const names = new Map<number, string>();
    dashboard.data?.data.cameras.forEach((c) => names.set(c.camera_id, c.name));
    cameras.data?.data.forEach((c) => names.set(c.id, c.name));
    recent.data?.data.forEach((e) => e.camera_name && names.set(e.camera_id, e.camera_name));
    return names;
  }, [dashboard.data, cameras.data, recent.data]);

  const summary = dashboard.data?.data;
  const loadLevels = { ...(summary?.load_levels ?? {}) };
  for (const [node, message] of Object.entries(liveLoad)) loadLevels[node] = message.level;

  return (
    <>
      <PageHeader
        title="Dashboard"
        description={summary ? `Today, ${formatDate(summary.work_date)}` : "Today's attendance at a glance"}
      />
      {dashboard.isError ? (
        <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} />
      ) : (
        <div className="space-y-4">
          <KpiCards summary={summary} />
          <div className="grid gap-4 xl:grid-cols-3">
            <div className="space-y-4 xl:col-span-2">
              {summary ? (
                <div className="grid gap-4 lg:grid-cols-2">
                  <HourlyArrivalsChart data={summary.hourly_arrivals} />
                  <DepartmentAttendanceChart data={summary.departments} />
                </div>
              ) : (
                <Skeleton className="h-80" />
              )}
              {summary && <CameraHealthStrip cameras={summary.cameras} loadLevels={loadLevels} />}
            </div>
            <LiveEventFeed events={feed} cameraNames={cameraNames} showSnapshots={canSeeEvents} />
          </div>
        </div>
      )}
    </>
  );
}
