import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  createCamera,
  deleteCamera,
  listCameras,
  liveView,
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
