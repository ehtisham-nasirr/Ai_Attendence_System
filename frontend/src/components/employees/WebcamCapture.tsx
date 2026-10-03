import { Camera, CameraOff } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { measureQuality, type QualityHint } from "@/lib/imageQuality";
import { cn } from "@/lib/utils";

const ANALYSE_EVERY_MS = 500;
const ANALYSE_WIDTH = 160;

/**
 * Webcam capture with a face-guide oval and live quality hints (§13 screen 5). Frames never leave
 * the browser until the user captures and uploads them.
 */
export function WebcamCapture({ onCapture, disabled }: { onCapture: (file: File) => void; disabled?: boolean }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<QualityHint | null>(null);

  const stop = useCallback(() => {
    setStream((current) => {
      current?.getTracks().forEach((track) => track.stop());
      return null;
    });
    setHint(null);
  }, []);

  const start = async () => {
    setError(null);
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
        audio: false,
      });
      setStream(media);
    } catch {
      setError("The camera could not be opened. Allow camera access in the browser, or upload photos instead.");
    }
  };

  useEffect(() => {
    const video = videoRef.current;
    if (video && stream) {
      video.srcObject = stream;
      void video.play();
    }
  }, [stream]);

  useEffect(() => stop, [stop]);

  useEffect(() => {
    if (!stream) return;
    const timer = setInterval(() => {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (!video || !canvas || video.videoWidth === 0) return;
      const height = Math.round((ANALYSE_WIDTH * video.videoHeight) / video.videoWidth);
      canvas.width = ANALYSE_WIDTH;
      canvas.height = height;
      const context = canvas.getContext("2d", { willReadFrequently: true });
      if (!context) return;
      context.drawImage(video, 0, 0, ANALYSE_WIDTH, height);
      setHint(measureQuality(context.getImageData(0, 0, ANALYSE_WIDTH, height).data, ANALYSE_WIDTH, height));
    }, ANALYSE_EVERY_MS);
    return () => clearInterval(timer);
  }, [stream]);

  const capture = () => {
    const video = videoRef.current;
    if (!video || video.videoWidth === 0) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (blob) onCapture(new File([blob], `webcam-${Date.now()}.jpg`, { type: "image/jpeg" }));
      },
      "image/jpeg",
      0.92,
    );
  };

  return (
    <div className="space-y-3">
      <div className="relative mx-auto aspect-video w-full max-w-xl overflow-hidden rounded-lg bg-black">
        {stream ? (
          <>
            <video ref={videoRef} muted playsInline className="size-full -scale-x-100 object-cover" aria-label="Webcam preview" />
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 size-full" aria-hidden>
              <defs>
                <mask id="oval-mask">
                  <rect width="100" height="100" fill="white" />
                  <ellipse cx="50" cy="50" rx="18" ry="40" fill="black" />
                </mask>
              </defs>
              <rect width="100" height="100" fill="black" opacity="0.45" mask="url(#oval-mask)" />
              <ellipse
                cx="50"
                cy="50"
                rx="18"
                ry="40"
                fill="none"
                strokeWidth="0.8"
                className={cn(hint?.ok ? "stroke-status-ok" : "stroke-status-warn")}
              />
            </svg>
          </>
        ) : (
          <div className="flex size-full flex-col items-center justify-center gap-2 text-sm text-white/80">
            <CameraOff className="size-8" aria-hidden />
            Camera is off
          </div>
        )}
      </div>
      <canvas ref={canvasRef} className="hidden" />
      {hint && (
        <p role="status" className={cn("text-center text-sm", hint.ok ? "text-status-ok" : "text-status-warn")}>
          {hint.message}
        </p>
      )}
      {error && (
        <p role="alert" className="text-destructive text-center text-sm">
          {error}
        </p>
      )}
      <div className="flex justify-center gap-2">
        {stream ? (
          <>
            <Button onClick={capture} disabled={disabled}>
              <Camera aria-hidden /> Capture
            </Button>
            <Button variant="outline" onClick={stop}>
              Stop camera
            </Button>
          </>
        ) : (
          <Button variant="outline" onClick={() => void start()}>
            <Camera aria-hidden /> Start webcam
          </Button>
        )}
      </div>
    </div>
  );
}
