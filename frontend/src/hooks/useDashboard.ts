import { useQuery } from "@tanstack/react-query";

import { dashboardSummary } from "@/api/generated/endpoints";

/** Today's KPIs; kept fresh by /ws/live invalidations, with a slow poll as fallback. */
export function useDashboard(locationId: number | null) {
  return useQuery({
    queryKey: ["dashboard", { locationId }],
    queryFn: () => dashboardSummary(locationId ? { location_id: locationId } : undefined),
    refetchInterval: 60_000,
  });
}
