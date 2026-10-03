import type { CameraHealthItem, CameraMode, CameraStatus } from "@/api/generated/model";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cameraModeLabel, cameraStatusLabel } from "@/lib/labels";

/** One chip per camera: status + mode + FPS (§13 screen 2, FR-3). */
export function CameraHealthStrip({
  cameras,
  loadLevels,
}: {
  cameras: CameraHealthItem[];
  loadLevels: Record<string, number>;
}) {
  const degraded = Object.entries(loadLevels).filter(([, level]) => level > 1);
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">Camera health</CardTitle>
        {degraded.length > 0 && (
          <StatusBadge
            tone="warn"
            label={`Reduced processing: ${degraded.map(([node, level]) => `${node} level ${level}`).join(", ")}`}
          />
        )}
      </CardHeader>
      <CardContent>
        {cameras.length === 0 ? (
          <p className="text-muted-foreground text-sm">No cameras configured yet.</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {cameras.map((camera) => {
              const status = cameraStatusLabel[camera.status as CameraStatus] ?? cameraStatusLabel.unknown;
              const mode = camera.mode ? cameraModeLabel[camera.mode as CameraMode] : null;
              return (
                <li key={camera.camera_id} className="bg-muted/40 flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm">
                  <span className="font-medium">{camera.name}</span>
                  <StatusBadge label={status.label} tone={status.tone} />
                  {mode && camera.status === "online" && (
                    <span className="text-muted-foreground text-xs">
                      {mode.label}
                      {camera.fps_actual !== null && ` · ${camera.fps_actual.toFixed(1)} fps`}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
