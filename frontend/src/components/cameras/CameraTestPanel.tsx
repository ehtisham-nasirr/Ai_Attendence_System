import { PlugZap } from "lucide-react";

import type { CameraTestOut } from "@/api/generated/model";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";

/** FR-2: connection test result with the live snapshot. */
export function CameraTestPanel({
  result,
  pending,
  onTest,
  disabled,
}: {
  result: CameraTestOut | null;
  pending: boolean;
  onTest: () => void;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-3 rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onTest} disabled={pending || disabled}>
          <PlugZap aria-hidden /> {pending ? "Testing…" : "Test connection"}
        </Button>
        {result &&
          (result.ok ? (
            <StatusBadge
              tone="ok"
              label={`Connected · ${result.width ?? "?"}×${result.height ?? "?"}${result.codec ? ` · ${result.codec}` : ""}`}
            />
          ) : (
            <StatusBadge tone="bad" label="Connection failed" />
          ))}
      </div>
      {result && !result.ok && result.error && (
        <p role="alert" className="text-destructive text-sm">
          {result.error}
        </p>
      )}
      {disabled && <p className="text-muted-foreground text-xs">Save the camera to test the stream.</p>}
    </div>
  );
}
