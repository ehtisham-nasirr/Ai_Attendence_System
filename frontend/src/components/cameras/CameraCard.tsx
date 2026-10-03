import { Pencil, Trash2 } from "lucide-react";

import type { CameraOut } from "@/api/generated/model";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cameraModeLabel, cameraRoleLabel, cameraStatusLabel } from "@/lib/labels";

export function CameraCard({
  camera,
  locationName,
  nodeLevel,
  onEdit,
  onDelete,
}: {
  camera: CameraOut;
  locationName: string;
  nodeLevel: number | undefined;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const status = cameraStatusLabel[camera.status];
  const runtime = camera.runtime;
  const mode = runtime ? cameraModeLabel[runtime.mode] : null;
  return (
    <Card className="gap-3">
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div className="min-w-0">
          <CardTitle className="truncate text-base">{camera.name}</CardTitle>
          <p className="text-muted-foreground truncate text-xs">
            {cameraRoleLabel[camera.role]} · {locationName} · {camera.stream_host}
          </p>
        </div>
        <div className="flex shrink-0 gap-1">
          <Button variant="ghost" size="icon" className="size-8" aria-label={`Edit ${camera.name}`} onClick={onEdit}>
            <Pencil />
          </Button>
          <Button variant="ghost" size="icon" className="size-8" aria-label={`Delete ${camera.name}`} onClick={onDelete}>
            <Trash2 />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-1.5">
          <StatusBadge label={status.label} tone={status.tone} />
          {mode && camera.status === "online" && <StatusBadge label={mode.label} tone={mode.tone} />}
          {camera.liveness_enabled && <StatusBadge label="Liveness" tone="info" />}
        </div>
        <dl className="grid grid-cols-3 gap-2 text-xs">
          <div>
            <dt className="text-muted-foreground">FPS</dt>
            <dd className="font-medium tabular-nums">
              {runtime ? `${runtime.fps_actual.toFixed(1)} / ${runtime.fps_target}` : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Lag</dt>
            <dd className="font-medium tabular-nums">{runtime ? `${runtime.lag_seconds.toFixed(1)} s` : "—"}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Faces today</dt>
            <dd className="font-medium tabular-nums">{runtime?.faces_today ?? "—"}</dd>
          </div>
          <div className="col-span-3">
            <dt className="text-muted-foreground">Engine node</dt>
            <dd className="font-medium">
              {camera.engine_node}
              {nodeLevel !== undefined && ` · load level ${nodeLevel}${nodeLevel > 1 ? " (reduced)" : ""}`}
            </dd>
          </div>
        </dl>
        {runtime?.last_error && camera.status !== "online" && (
          <p className="text-destructive text-xs" role="status">
            {runtime.last_error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
