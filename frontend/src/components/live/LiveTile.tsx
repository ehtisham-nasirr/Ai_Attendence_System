import { Expand, VideoOff } from "lucide-react";
import { useEffect, useState } from "react";

import type { CameraOut } from "@/api/generated/model";
import { DetectionOverlay } from "@/components/live/DetectionOverlay";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useLiveView } from "@/hooks/useCameras";
import { useLiveCameraStatus } from "@/hooks/useLiveFeed";
import { cameraModeLabel, cameraStatusLabel } from "@/lib/labels";
import { startWhep, type WhepSession } from "@/lib/whep";
import { cn } from "@/lib/utils";

// Every tile has the same frame; a 4:3 or 5:4 camera is letterboxed inside it, not stretched.
const FRAME_ASPECT = 16 / 9;

/** One camera: WebRTC video via MediaMTX, overlay boxes, status. */
export function LiveTile({
  camera,
  onExpand,
  large = false,
}: {
  camera: CameraOut;
  onExpand?: () => void;
  large?: boolean;
}) {
  const [aspect, setAspect] = useState(16 / 9);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const liveStatus = useLiveCameraStatus()[camera.id];
  const online = liveStatus ? liveStatus.connected : camera.status === "online";
  const live = useLiveView(camera.id, online && camera.is_enabled);
  const url = live.data?.data.webrtc_url;
  const token = live.data?.data.token;

  useEffect(() => {
    if (!url || !token) return;
    let session: WhepSession | null = null;
    let cancelled = false;
    startWhep(
      url,
      token,
      (incoming) => {
        if (cancelled) return;
        setStream(incoming);
        setError(null);
      },
      () => !cancelled && setError("The live stream dropped. Retrying…"),
    )
      .then((started) => {
        if (cancelled) started.stop();
        else session = started;
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Live view unavailable");
      });
    return () => {
      cancelled = true;
      session?.stop();
    };
    // A refreshed token (every 90 s) does not restart a working session; `retry` does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, retry]);

  useEffect(() => {
    if (!error) return;
    const timer = setTimeout(() => setRetry((n) => n + 1), 10_000);
    return () => clearTimeout(timer);
  }, [error]);

  const status = online ? cameraStatusLabel.online : cameraStatusLabel[camera.status === "online" ? "offline" : camera.status];
  const mode = liveStatus?.mode ?? camera.runtime?.mode;
  return (
    <div className="bg-card overflow-hidden rounded-lg border">
      <div className="relative flex aspect-video items-center justify-center bg-black">
        {online && !error ? (
          // The overlay boxes are fractions of the video picture, so they sit in a box of the video's shape.
          <div
            className="relative max-h-full max-w-full"
            style={aspect >= FRAME_ASPECT ? { width: "100%", aspectRatio: aspect } : { height: "100%", aspectRatio: aspect }}
          >
            <video
              ref={(video) => {
                if (video && stream && video.srcObject !== stream) video.srcObject = stream;
              }}
              autoPlay
              muted
              playsInline
              className="absolute inset-0 size-full"
              aria-label={`Live video of ${camera.name}`}
              onLoadedMetadata={(event) => {
                const video = event.currentTarget;
                if (video.videoWidth && video.videoHeight) setAspect(video.videoWidth / video.videoHeight);
              }}
            />
            <DetectionOverlay cameraId={camera.id} />
          </div>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-sm text-white/70">
            <VideoOff className="size-8" aria-hidden />
            {error ?? (camera.is_enabled ? "Camera offline" : "Camera disabled")}
          </div>
        )}
        {onExpand && (
          <button
            type="button"
            onClick={onExpand}
            className="absolute top-2 right-2 rounded bg-black/50 p-1 text-white hover:bg-black/70"
            aria-label={`Expand ${camera.name}`}
          >
            <Expand className="size-4" />
          </button>
        )}
      </div>
      <div className={cn("flex items-center justify-between gap-2 px-3 py-2", large && "py-3")}>
        <p className="truncate text-sm font-medium">{camera.name}</p>
        <div className="flex shrink-0 gap-1">
          <StatusBadge label={status.label} tone={status.tone} />
          {online && mode && <StatusBadge label={cameraModeLabel[mode].label} tone={cameraModeLabel[mode].tone} />}
        </div>
      </div>
    </div>
  );
}
