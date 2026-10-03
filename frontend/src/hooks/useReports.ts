import { useMutation, useQuery } from "@tanstack/react-query";

import { getJobFile, getReport } from "@/api/generated/endpoints";
import type { GetReportParams, ReportExportAccepted, ReportOut, ReportType } from "@/api/generated/model";
import { downloadBlob } from "@/lib/csv";

export type ReportFilters = Omit<GetReportParams, "format">;

function isReport(data: ReportOut | ReportExportAccepted): data is ReportOut {
  return "columns" in data;
}

/** Preview: first 500 rows plus summary and chart (FR-30). Runs when `params` is set. */
export function useReport(reportType: ReportType, params: ReportFilters | null) {
  return useQuery({
    queryKey: ["reports", reportType, params],
    queryFn: async () => {
      const response = await getReport(reportType, params as ReportFilters);
      if (!isReport(response.data)) throw new Error("Unexpected export response for a preview.");
      return response.data;
    },
    enabled: params !== null,
  });
}

/** FR-31 export: queues a Celery job (202) and returns its id (polled by ExportButtons). */
export function useStartExport() {
  return useMutation({
    mutationFn: async ({ reportType, params, format }: { reportType: ReportType; params: ReportFilters; format: "xlsx" | "pdf" }) => {
      const response = await getReport(reportType, { ...params, format });
      if (isReport(response.data)) throw new Error("The server returned data instead of starting an export.");
      return response.data.job_id;
    },
  });
}

/** Downloads a finished job's file (the session cookie authorises it). */
export async function downloadJobFile(jobId: string, filename: string): Promise<void> {
  // The generated function is typed `void` because the spec has no schema for binary bodies.
  const blob = (await getJobFile(jobId, { responseType: "blob" })) as unknown as Blob;
  downloadBlob(blob, filename);
}
