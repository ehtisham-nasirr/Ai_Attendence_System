import { QueryClient } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  applyLiveMessage,
  backoffDelay,
  DETECTION_TTL_MS,
  LIVE_KEYS,
  parseLiveMessage,
  RECENT_EVENTS_LIMIT,
  throttledInvalidator,
  type Detection,
  type LiveMessage,
  type RecognitionCreatedData,
} from "@/lib/live";

function recognition(id: number, overrides: Partial<RecognitionCreatedData> = {}): LiveMessage {
  return {
    type: "RecognitionCreated",
    sent_at: "2026-10-05T04:40:00Z",
    data: {
      event_id: id,
      camera_id: 1,
      status: "recognized",
      employee_id: 7,
      employee_code: "E-7",
      employee_name: "Sara",
      department_id: 1,
      confidence: 0.71,
      captured_at: "2026-10-05T04:40:00Z",
      bbox: [0.1, 0.2, 0.1, 0.2],
      snapshot_available: true,
      ...overrides,
    },
  };
}

describe("parseLiveMessage", () => {
  it("accepts the four documented types only", () => {
    expect(parseLiveMessage(JSON.stringify(recognition(1)))?.type).toBe("RecognitionCreated");
    expect(parseLiveMessage(JSON.stringify({ type: "SomethingElse", data: {} }))).toBeNull();
    expect(parseLiveMessage("not json")).toBeNull();
    expect(parseLiveMessage(42)).toBeNull();
  });
});

describe("applyLiveMessage", () => {
  it("prepends recognitions to the feed, de-duplicates and caps it", () => {
    const client = new QueryClient();
    const invalidate = vi.fn();
    for (let id = 1; id <= RECENT_EVENTS_LIMIT + 5; id += 1) applyLiveMessage(client, recognition(id), invalidate);
    applyLiveMessage(client, recognition(RECENT_EVENTS_LIMIT + 5), invalidate);
    const feed = client.getQueryData<RecognitionCreatedData[]>(LIVE_KEYS.recentEvents) ?? [];
    expect(feed).toHaveLength(RECENT_EVENTS_LIMIT);
    expect(feed[0].event_id).toBe(RECENT_EVENTS_LIMIT + 5);
    expect(new Set(feed.map((e) => e.event_id)).size).toBe(RECENT_EVENTS_LIMIT);
    expect(invalidate).toHaveBeenCalledWith(["dashboard"]);
  });

  it("keeps overlay boxes per camera and drops expired ones", () => {
    const client = new QueryClient();
    applyLiveMessage(client, recognition(1), vi.fn(), 1_000);
    applyLiveMessage(client, recognition(2), vi.fn(), 1_000 + DETECTION_TTL_MS + 1);
    const boxes = client.getQueryData<Record<number, Detection[]>>(LIVE_KEYS.detections)?.[1] ?? [];
    expect(boxes.map((d) => d.event_id)).toEqual([2]);
  });

  it("refreshes the unknown-face queue only for unknown faces", () => {
    const client = new QueryClient();
    const invalidate = vi.fn();
    applyLiveMessage(client, recognition(1), invalidate);
    expect(invalidate).not.toHaveBeenCalledWith(["unknown-faces"]);
    applyLiveMessage(client, recognition(2, { status: "unknown", employee_id: null }), invalidate);
    expect(invalidate).toHaveBeenCalledWith(["unknown-faces"]);
  });

  it("stores camera status and load level, and invalidates attendance on updates", () => {
    const client = new QueryClient();
    const invalidate = vi.fn();
    applyLiveMessage(
      client,
      { type: "CameraStatusChanged", sent_at: "", data: { camera_id: 3, mode: "ACTIVE", connected: true, fps_actual: 4, engine_node: "node-1" } },
      invalidate,
    );
    applyLiveMessage(client, { type: "LoadLevelChanged", sent_at: "", data: { engine_node: "node-1", level: 3, cpu_percent: 91 } }, invalidate);
    applyLiveMessage(
      client,
      {
        type: "AttendanceUpdated",
        sent_at: "",
        data: { attendance_day_id: 1, employee_id: 7, department_id: 1, work_date: "2026-10-05", status: "late", check_in_at: null, check_out_at: null },
      },
      invalidate,
    );
    expect(client.getQueryData<Record<number, { mode: string }>>(LIVE_KEYS.cameraStatus)?.[3].mode).toBe("ACTIVE");
    expect(client.getQueryData<Record<string, { level: number }>>(LIVE_KEYS.loadLevels)?.["node-1"].level).toBe(3);
    expect(invalidate).toHaveBeenCalledWith(["attendance"]);
    expect(invalidate).toHaveBeenCalledWith(["cameras"]);
  });
});

describe("backoffDelay", () => {
  it("doubles from 1 s and caps at 30 s plus jitter", () => {
    expect(backoffDelay(0, () => 0)).toBe(1_000);
    expect(backoffDelay(3, () => 0)).toBe(8_000);
    expect(backoffDelay(10, () => 0)).toBe(30_000);
    expect(backoffDelay(10, () => 1)).toBe(36_000);
  });
});

describe("throttledInvalidator", () => {
  afterEach(() => vi.useRealTimers());

  it("invalidates each key once per window", () => {
    vi.useFakeTimers();
    const client = new QueryClient();
    const spy = vi.spyOn(client, "invalidateQueries");
    const invalidate = throttledInvalidator(client, 1_000);
    invalidate(["dashboard"]);
    invalidate(["dashboard"]);
    invalidate(["attendance"]);
    vi.advanceTimersByTime(1_000);
    expect(spy).toHaveBeenCalledTimes(2);
    invalidate(["dashboard"]);
    invalidate.cancel();
    vi.advanceTimersByTime(1_000);
    expect(spy).toHaveBeenCalledTimes(2);
  });
});
