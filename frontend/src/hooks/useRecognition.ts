import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { bulkReviewUnknownFaces, listEvents, listUnknownFaceGroups, voidEvent } from "@/api/generated/endpoints";
import type {
  ApiResponseUnknownFaceBulkResult,
  ListEventsParams,
  ListUnknownFaceGroupsParams,
  UnknownFaceBulkAction,
} from "@/api/generated/model";
import { fetchAllPages } from "@/lib/query";

export function useEvents(params: ListEventsParams) {
  return useQuery({
    queryKey: ["events", params],
    queryFn: () => listEvents(params),
    placeholderData: keepPreviousData,
  });
}

export function exportEvents(params: ListEventsParams) {
  return fetchAllPages((page, page_size) => listEvents({ ...params, page, page_size }));
}

export function useVoidEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => voidEvent(id, { reason }),
    onSuccess: (result) => {
      toast.success(result.message);
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      void queryClient.invalidateQueries({ queryKey: ["attendance"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

/** §13 screen 9: one card per group of similar faces over the whole queue; pages count groups. */
export function useUnknownFaceGroups(params: ListUnknownFaceGroupsParams) {
  return useQuery({
    // Starts with "unknown-faces", so /ws/live invalidations for new unknown faces refresh it.
    queryKey: ["unknown-faces", "groups", params],
    queryFn: () => listUnknownFaceGroups(params),
    placeholderData: keepPreviousData,
  });
}

function skippedDescription(result: ApiResponseUnknownFaceBulkResult): string | null {
  const { skipped } = result.data;
  if (skipped.length === 0) return null;
  const reviewed = skipped.filter((face) => face.reason === "already_reviewed").length;
  const missing = skipped.length - reviewed;
  const parts: string[] = [];
  if (reviewed > 0) parts.push(`${reviewed} already reviewed`);
  if (missing > 0) parts.push(`${missing} not found`);
  return `Skipped faces: ${parts.join(", ")}.`;
}

/** FR-27: one decision (assign or dismiss) for the faces of a group card. */
export function useUnknownFaceActions() {
  const queryClient = useQueryClient();
  return {
    bulk: useMutation({
      mutationFn: (body: UnknownFaceBulkAction) => bulkReviewUnknownFaces(body),
      onSuccess: (result) => {
        const description = skippedDescription(result);
        if (description) toast.warning(result.message, { description });
        else toast.success(result.message);
        const added = result.data.gallery_added ?? 0;
        const reason = result.data.gallery_rejection_reason;
        if (added > 0) toast.success(`${added} photo(s) added to the employee's gallery as assigned photos.`);
        else if (reason) toast.warning(`Assigned, but not added to the gallery: ${reason.replaceAll("_", " ")}`);
        void queryClient.invalidateQueries({ queryKey: ["unknown-faces"] });
        void queryClient.invalidateQueries({ queryKey: ["attendance"] });
        void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      },
    }),
  };
}
