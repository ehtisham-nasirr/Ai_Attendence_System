import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { assignUnknown, listEvents, listUnknownFaces, updateUnknown, voidEvent } from "@/api/generated/endpoints";
import { UnknownFaceUpdateValue, type ListEventsParams, type ListUnknownFacesParams } from "@/api/generated/model";
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

export function useUnknownFaces(params: ListUnknownFacesParams) {
  return useQuery({
    queryKey: ["unknown-faces", params],
    queryFn: () => listUnknownFaces(params),
    placeholderData: keepPreviousData,
  });
}

export function useUnknownFaceActions() {
  const queryClient = useQueryClient();
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["unknown-faces"] });
    void queryClient.invalidateQueries({ queryKey: ["attendance"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };
  return {
    assign: useMutation({
      mutationFn: ({ id, employeeId, addToGallery }: { id: number; employeeId: number; addToGallery: boolean }) =>
        assignUnknown(id, { employee_id: employeeId, add_to_gallery: addToGallery }),
      onSuccess: (result) => {
        const reason = result.data.gallery_rejection_reason;
        if (reason) toast.warning(`Assigned, but not added to the gallery: ${reason}`);
        else toast.success(result.message);
        refresh();
      },
    }),
    dismiss: useMutation({
      mutationFn: (id: number) => updateUnknown(id, UnknownFaceUpdateValue),
      onSuccess: () => {
        toast.success("Unknown face dismissed.");
        refresh();
      },
    }),
  };
}
