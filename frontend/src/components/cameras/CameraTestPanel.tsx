import { PlugZap } from "lucide-react";

import type { CameraTestOut } from "@/api/generated/model";
import { StatusBadge } from "@/components/common/StatusBadge";
import { connectionHint } from "@/lib/cameraHints";
import { Button } from "@/components/ui/button";

/** FR-2: connection test result with the live snapshot. */
export function CameraTestPanel({
  result,
  pending,
  onTest,
  disabledReason,
}: {
  result: CameraTestOut | null;
  pending: boolean;
  onTest: () => void;
  /** Why the test cannot run yet; the test always uses the saved stream link. */
  disabledReason?: string;
}) {
  return (
    <div className="space-y-3 rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onTest} disabled={pending || Boolean(disabledReason)}>
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
        <div role="alert" className="space-y-1 text-sm">
          <p className="text-destructive">{result.error}</p>
          {connectionHint(result.error) && <p className="text-muted-foreground">{connectionHint(result.error)}</p>}
        </div>
      )}
      {disabledReason && <p className="text-muted-foreground text-xs">{disabledReason}</p>}
    </div>
  );
}
