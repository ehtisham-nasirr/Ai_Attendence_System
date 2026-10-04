import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  createCamera,
  deleteCamera,
  listCameras,
  liveView,
  streamUrls,
  testCamera,
  updateCamera,
} from "@/api/generated/endpoints";
import type { CameraCreate, CameraUpdate, ListCamerasParams } from "@/api/generated/model";

export function useCameras(params: ListCamerasParams, refetchInterval: number | false = 30_000) {
  return useQuery({
    queryKey: ["cameras", params],
    queryFn: () => listCameras(params),
    placeholderData: keepPreviousData,
    refetchInterval, // health also arrives over /ws/live; this is the fallback
  });
}

export function useCameraMutations() {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["cameras"] });
  return {
    create: useMutation({
      mutationFn: (body: CameraCreate) => createCamera(body),
      onSuccess: (result) => {
        toast.success(result.message);
        void refresh();
      },
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: CameraUpdate }) => updateCamera(id, body),
      onSuccess: (result) => {
        toast.success(result.message);
        void refresh();
      },
    }),
    remove: useMutation({
      mutationFn: (id: number) => deleteCamera(id),
      onSuccess: () => {
        toast.success("Camera deleted.");
        void refresh();
      },
    }),
    test: useMutation({
      mutationFn: ({ id, useSubstream }: { id: number; useSubstream: boolean }) =>
        testCamera(id, { use_substream: useSubstream }),
    }),
  };
}

/**
 * Saved stream links (with credentials) for the edit form, camera managers only (Q63). Loaded once per
 * opened form and not kept in the cache afterwards; no refetch on focus, so typing is never overwritten.
 */
export function useCameraStreamUrls(cameraId: number | undefined) {
  return useQuery({
    queryKey: ["camera-stream-urls", cameraId],
    queryFn: () => streamUrls(cameraId as number),
    enabled: cameraId !== undefined,
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
    refetchOnWindowFocus: false,
  });
}

/** Short-lived WebRTC (WHEP) URL + token for one camera tile; refreshed before it expires. */
export function useLiveView(cameraId: number, enabled: boolean) {
  return useQuery({
    queryKey: ["cameras", "live", cameraId],
    queryFn: () => liveView(cameraId),
    enabled,
    staleTime: 60_000,
    refetchInterval: 90_000,
  });
}
