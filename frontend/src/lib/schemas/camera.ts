import { z } from "zod";

const streamUrl = /^(rtsp|rtsps|file):\/\/\S+$/;

export const operatingWindowSchema = z.object({
  days: z.array(z.number().int().min(1).max(7)).min(1, "Pick at least one day"),
  start: z.string().regex(/^\d{2}:\d{2}$/, "HH:MM"),
  end: z.string().regex(/^\d{2}:\d{2}$/, "HH:MM"),
});
export type OperatingWindow = z.infer<typeof operatingWindowSchema>;

export function cameraSchema(isNew: boolean) {
  return z.object({
    name: z.string().trim().min(1, "Name is required").max(120),
    location_id: z.string().min(1, "Choose a location"),
    role: z.enum(["ENTRY", "EXIT", "ENTRY_EXIT", "GENERAL"]),
    // On edit an empty URL keeps the stored one (credentials are never sent back to the browser).
    rtsp_url: isNew
      ? z.string().trim().regex(streamUrl, "Use rtsp://user:password@host:554/path")
      : z.union([z.literal(""), z.string().trim().regex(streamUrl, "Use rtsp://user:password@host:554/path")]),
    substream_url: z.union([z.literal(""), z.string().trim().regex(streamUrl, "Use an rtsp:// URL")]),
    clear_substream: z.boolean(),
    engine_node: z.string().trim().min(1).max(64),
    priority: z.number().int().min(0).max(100),
    always_on: z.boolean(),
    operating_hours: z.array(operatingWindowSchema),
    roi_polygon: z.array(z.tuple([z.number().min(0).max(1), z.number().min(0).max(1)])),
    use_default_fps: z.boolean(),
    fps: z.number().gt(0).max(15),
    use_default_threshold: z.boolean(),
    match_threshold: z.number().gt(0).lt(1),
    liveness_enabled: z.boolean(),
    is_enabled: z.boolean(),
  });
}
export type CameraFormValues = z.infer<ReturnType<typeof cameraSchema>>;
