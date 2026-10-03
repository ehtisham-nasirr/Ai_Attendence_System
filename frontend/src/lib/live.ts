/**
 * `/ws/live` message handling (standards/04, 08). Messages update or invalidate the TanStack Query
 * cache; nothing keeps a separate copy of server data.
 */
import type { QueryClient, QueryKey } from "@tanstack/react-query";

import type { AttendanceStatus, CameraMode, RecognitionStatus } from "@/api/generated/model";

export interface RecognitionCreatedData {
  event_id: number;
  camera_id: number;
  status: RecognitionStatus;
  employee_id: number | null;
  employee_code: string | null;
  employee_name: string | null;
  department_id: number | null;
  confidence: number;
  captured_at: string;
  /** Normalised [x, y, width, height] in 0..1 of the frame, when the engine sent it. */
  bbox: number[] | null;
  snapshot_available: boolean;
}

export interface AttendanceUpdatedData {
  attendance_day_id: number;
  employee_id: number;
  department_id: number | null;
  work_date: string;
  status: AttendanceStatus | null;
  check_in_at: string | null;
  check_out_at: string | null;
}

export interface CameraStatusChangedData {
  camera_id: number;
  mode: CameraMode;
  connected: boolean;
  fps_actual: number;
  engine_node: string;
}

export interface LoadLevelChangedData {
  engine_node: string;
  level: number;
  cpu_percent: number;
}

export type LiveMessage =
  | { type: "RecognitionCreated"; data: RecognitionCreatedData; sent_at: string }
  | { type: "AttendanceUpdated"; data: AttendanceUpdatedData; sent_at: string }
  | { type: "CameraStatusChanged"; data: CameraStatusChangedData; sent_at: string }
  | { type: "LoadLevelChanged"; data: LoadLevelChangedData; sent_at: string };

export const LIVE_KEYS = {
  recentEvents: ["live", "recent-events"] as const,
  detections: ["live", "detections"] as const,
  cameraStatus: ["live", "camera-status"] as const,
  loadLevels: ["live", "load-levels"] as const,
};

export const RECENT_EVENTS_LIMIT = 50;
/** Overlay boxes older than this are dropped from the live view. */
export const DETECTION_TTL_MS = 4_000;

export interface Detection extends RecognitionCreatedData {
  received_at: number;
}

const MESSAGE_TYPES = new Set(["RecognitionCreated", "AttendanceUpdated", "CameraStatusChanged", "LoadLevelChanged"]);

export function parseLiveMessage(raw: unknown): LiveMessage | null {
  if (typeof raw !== "string") return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (
      parsed &&
      typeof parsed === "object" &&
      "type" in parsed &&
      "data" in parsed &&
      MESSAGE_TYPES.has(String((parsed as { type: unknown }).type))
    ) {
      return parsed as LiveMessage;
    }
  } catch {
    // ignore malformed frames; the REST API stays authoritative
  }
  return null;
}

/** Reconnect delay: 1 s, 2 s, 4 s ... capped at 30 s, with up to 20 % jitter. */
export function backoffDelay(attempt: number, random: () => number = Math.random): number {
  const base = Math.min(30_000, 1_000 * 2 ** Math.max(0, attempt));
  return Math.round(base * (1 + 0.2 * random()));
}

export type Invalidate = (key: QueryKey) => void;

/** Applies one message to the cache. `invalidate` may be throttled by the caller. */
export function applyLiveMessage(
  client: QueryClient,
  message: LiveMessage,
  invalidate: Invalidate,
  now: number = Date.now(),
): void {
  switch (message.type) {
    case "RecognitionCreated": {
      const data = message.data;
      client.setQueryData<RecognitionCreatedData[]>(LIVE_KEYS.recentEvents, (previous = []) =>
        [data, ...previous.filter((e) => e.event_id !== data.event_id)].slice(0, RECENT_EVENTS_LIMIT),
      );
      if (data.bbox) {
        client.setQueryData<Record<number, Detection[]>>(LIVE_KEYS.detections, (previous = {}) => {
          const fresh = (previous[data.camera_id] ?? []).filter((d) => now - d.received_at < DETECTION_TTL_MS);
          return { ...previous, [data.camera_id]: [...fresh, { ...data, received_at: now }] };
        });
      }
      invalidate(["dashboard"]);
      if (data.status === "unknown") invalidate(["unknown-faces"]);
      invalidate(["events"]);
      break;
    }
    case "AttendanceUpdated":
      invalidate(["attendance"]);
      invalidate(["dashboard"]);
      break;
    case "CameraStatusChanged":
      client.setQueryData<Record<number, CameraStatusChangedData>>(LIVE_KEYS.cameraStatus, (previous = {}) => ({
        ...previous,
        [message.data.camera_id]: message.data,
      }));
      invalidate(["cameras"]);
      invalidate(["dashboard"]);
      break;
    case "LoadLevelChanged":
      client.setQueryData<Record<string, LoadLevelChangedData>>(LIVE_KEYS.loadLevels, (previous = {}) => ({
        ...previous,
        [message.data.engine_node]: message.data,
      }));
      invalidate(["dashboard"]);
      break;
  }
}

/** Invalidates each key at most once per `windowMs`, so a burst of arrivals refetches once. */
export function throttledInvalidator(client: QueryClient, windowMs = 3_000): Invalidate & { cancel: () => void } {
  const timers = new Map<string, ReturnType<typeof setTimeout>>();
  const invalidate = ((key: QueryKey) => {
    const id = JSON.stringify(key);
    if (timers.has(id)) return;
    timers.set(
      id,
      setTimeout(() => {
        timers.delete(id);
        void client.invalidateQueries({ queryKey: key });
      }, windowMs),
    );
  }) as Invalidate & { cancel: () => void };
  invalidate.cancel = () => {
    timers.forEach(clearTimeout);
    timers.clear();
  };
  return invalidate;
}
