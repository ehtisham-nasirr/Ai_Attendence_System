import { useEffect, useState } from "react";

import { useCameraDetections } from "@/hooks/useLiveFeed";
import { formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Boxes from recent RecognitionCreated messages: green = known, amber = unknown (§13 screen 3). */
export function DetectionOverlay({ cameraId }: { cameraId: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, []);
  const detections = useCameraDetections(cameraId, now);
  return (
    <div className="pointer-events-none absolute inset-0" aria-hidden>
      {detections.map((detection) => {
        if (!detection.bbox) return null;
        const [x, y, w, h] = detection.bbox;
        const known = detection.status === "recognized";
        return (
          <div
            key={detection.event_id}
            className={cn("absolute rounded-sm border-2", known ? "border-status-ok" : "border-status-warn")}
            style={{ left: `${x * 100}%`, top: `${y * 100}%`, width: `${w * 100}%`, height: `${h * 100}%` }}
          >
            <span
              className={cn(
                "absolute -top-5 left-0 rounded-sm px-1 text-[11px] font-medium whitespace-nowrap text-white",
                known ? "bg-status-ok" : "bg-status-warn",
              )}
            >
              {known ? `${detection.employee_name ?? "Employee"} ${formatPercent(detection.confidence)}` : "Unknown"}
            </span>
          </div>
        );
      })}
    </div>
  );
}
