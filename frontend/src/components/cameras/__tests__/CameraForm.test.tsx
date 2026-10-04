import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import type { CameraOut, CameraUpdate } from "@/api/generated/model";
import { CameraForm } from "@/components/cameras/CameraForm";
import { ok, page } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { server } from "@/test/server";

const MAIN = "rtsp://admin:Pa%40ss@192.168.11.45:554/cam/realmonitor?channel=1&subtype=0";
const SUB = "rtsp://admin:Pa%40ss@192.168.11.45:554/cam/realmonitor?channel=1&subtype=1";

const camera: CameraOut = {
  id: 4,
  name: "ReceptionCam",
  location_id: 1,
  role: "ENTRY_EXIT",
  stream_host: "192.168.11.45:554",
  has_substream: true,
  engine_node: "node-1",
  priority: 0,
  operating_hours: null,
  roi_polygon: null,
  fps: null,
  match_threshold: null,
  liveness_enabled: false,
  is_enabled: true,
  status: "online",
  last_seen_at: null,
  created_at: "2026-10-04T10:00:00Z",
  runtime: null,
};

function mockCameraApi(): CameraUpdate[] {
  const updates: CameraUpdate[] = [];
  server.use(
    http.get("*/api/v1/locations", () =>
      HttpResponse.json(page([{ id: 1, name: "Lahore Office", timezone: "Asia/Karachi", address: null, created_at: "2026-01-01T00:00:00Z" }])),
    ),
    http.get("*/api/v1/cameras/4/stream-urls", () => HttpResponse.json(ok({ rtsp_url: MAIN, substream_url: SUB }))),
    http.put("*/api/v1/cameras/4", async ({ request }) => {
      updates.push((await request.json()) as CameraUpdate);
      return HttpResponse.json(ok(camera, "Camera updated."));
    }),
    http.post("*/api/v1/cameras/4/test", () => HttpResponse.json(ok({ ok: true }))),
  );
  return updates;
}

describe("Camera form stream links (Q63)", () => {
  it("shows the saved links and does not resend them when only other fields change", async () => {
    const updates = mockCameraApi();
    renderWithProviders(<CameraForm camera={camera} onSaved={vi.fn()} />);
    expect(await screen.findByDisplayValue(MAIN)).toBeInTheDocument();
    expect(screen.getByDisplayValue(SUB)).toBeInTheDocument();
    expect(screen.queryByText("Remove the stored sub-stream")).not.toBeInTheDocument();

    const name = screen.getByLabelText("Name");
    await userEvent.clear(name);
    await userEvent.type(name, "Reception");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(updates).toHaveLength(1));
    expect(updates[0].name).toBe("Reception");
    expect(updates[0].rtsp_url).toBeUndefined();
    expect(updates[0].substream_url).toBeUndefined();
    expect(updates[0].clear_substream).toBe(false);
    expect(screen.getByDisplayValue(MAIN)).toBeInTheDocument(); // still shown after saving
  });

  it("sends a changed link and removes the sub-stream when its field is cleared", async () => {
    const updates = mockCameraApi();
    renderWithProviders(<CameraForm camera={camera} onSaved={vi.fn()} />);
    const sub = await screen.findByDisplayValue(SUB);
    await userEvent.clear(sub);
    const main = screen.getByDisplayValue(MAIN);
    await userEvent.clear(main);
    await userEvent.type(main, MAIN.replace("192.168.11.45", "192.168.11.46"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(updates).toHaveLength(1));
    expect(updates[0].rtsp_url).toBe(MAIN.replace("192.168.11.45", "192.168.11.46"));
    expect(updates[0].clear_substream).toBe(true);
  });
});
