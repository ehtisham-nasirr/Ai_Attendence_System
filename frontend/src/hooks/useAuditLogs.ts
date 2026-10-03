import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { listAuditLogs } from "@/api/generated/endpoints";
import type { ListAuditLogsParams } from "@/api/generated/model";
import { fetchAllPages } from "@/lib/query";

export function useAuditLogs(params: ListAuditLogsParams) {
  return useQuery({
    queryKey: ["audit-logs", params],
    queryFn: () => listAuditLogs(params),
    placeholderData: keepPreviousData,
  });
}

export function exportAuditLogs(params: ListAuditLogsParams) {
  return fetchAllPages((page, page_size) => listAuditLogs({ ...params, page, page_size }));
}
