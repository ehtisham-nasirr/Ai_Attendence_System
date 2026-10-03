import { useQuery } from "@tanstack/react-query";
import { createContext, useContext } from "react";

import {
  DETECTION_TTL_MS,
  LIVE_KEYS,
  type CameraStatusChangedData,
  type Detection,
  type LoadLevelChangedData,
  type RecognitionCreatedData,
} from "@/lib/live";

export type LiveStatus = "connecting" | "open" | "closed" | "paused";

export const LiveStatusContext = createContext<LiveStatus>("closed");

/** Connection state of the one shared `/ws/live` socket (owned by LiveFeedProvider). */
export function useLiveFeed(): { status: LiveStatus } {
  return { status: useContext(LiveStatusContext) };
}

function useLiveCache<T>(key: readonly unknown[], empty: T): T {
  // Data is written by the live feed with setQueryData; the queryFn only seeds an empty value.
  const { data } = useQuery({ queryKey: key, queryFn: () => empty, staleTime: Infinity, gcTime: Infinity });
  return data ?? empty;
}

const NO_EVENTS: RecognitionCreatedData[] = [];
const NO_DETECTIONS: Record<number, Detection[]> = {};
const NO_STATUS: Record<number, CameraStatusChangedData> = {};
const NO_LOAD: Record<string, LoadLevelChangedData> = {};

export function useRecentEvents(): RecognitionCreatedData[] {
  return useLiveCache(LIVE_KEYS.recentEvents, NO_EVENTS);
}

export function useCameraDetections(cameraId: number, now: number): Detection[] {
  const all = useLiveCache(LIVE_KEYS.detections, NO_DETECTIONS);
  return (all[cameraId] ?? []).filter((d) => now - d.received_at < DETECTION_TTL_MS);
}

export function useLiveCameraStatus(): Record<number, CameraStatusChangedData> {
  return useLiveCache(LIVE_KEYS.cameraStatus, NO_STATUS);
}

export function useLiveLoadLevels(): Record<string, LoadLevelChangedData> {
  return useLiveCache(LIVE_KEYS.loadLevels, NO_LOAD);
}
