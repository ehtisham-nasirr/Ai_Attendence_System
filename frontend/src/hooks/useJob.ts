import { useQuery } from "@tanstack/react-query";

import { getJob } from "@/api/generated/endpoints";

/** Polls a background job (imports, exports) until it finishes. */
export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: ["jobs", jobId],
    queryFn: () => getJob(jobId as string),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.data.status;
      return status === "succeeded" || status === "failed" ? false : 1_500;
    },
  });
}
