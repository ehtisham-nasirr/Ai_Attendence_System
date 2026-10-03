import { Video } from "lucide-react";
import { useState } from "react";

import type { CameraOut } from "@/api/generated/model";
import { LiveTile } from "@/components/live/LiveTile";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useCameras } from "@/hooks/useCameras";
import { useLocationFilter } from "@/hooks/useLocationFilter";
import { useUrlState } from "@/hooks/useUrlState";
import { cn } from "@/lib/utils";

const LAYOUTS = [1, 4, 9, 16] as const;
const gridClass: Record<number, string> = {
  1: "grid-cols-1",
  4: "grid-cols-1 md:grid-cols-2",
  9: "grid-cols-2 lg:grid-cols-3",
  16: "grid-cols-2 md:grid-cols-3 xl:grid-cols-4",
};

/** §13 screen 3: 1/4/9/16 tiles over WebRTC; click a tile to expand it. */
export function LiveViewPage() {
  const url = useUrlState();
  const { locationId } = useLocationFilter();
  const layout = Number(url.get("layout") ?? 4);
  const tiles = (LAYOUTS as readonly number[]).includes(layout) ? layout : 4;
  const page = url.page;
  const cameras = useCameras({ location_id: locationId ?? undefined, page, page_size: tiles, sort: "name" });
  const [expanded, setExpanded] = useState<CameraOut | null>(null);
  const total = cameras.data?.pagination.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / tiles));

  return (
    <>
      <PageHeader
        title="Live view"
        description="Green boxes are recognised employees, amber boxes unknown faces."
        actions={
          <ToggleGroup
            type="single"
            variant="outline"
            value={String(tiles)}
            onValueChange={(value) => value && url.set({ layout: value })}
            aria-label="Tiles per page"
          >
            {LAYOUTS.map((count) => (
              <ToggleGroupItem key={count} value={String(count)} aria-label={`${count} tiles`}>
                {count}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        }
      />
      {cameras.isPending ? (
        <div className={cn("grid gap-3", gridClass[tiles])}>
          {Array.from({ length: Math.min(tiles, 4) }, (_, i) => (
            <Skeleton key={i} className="aspect-video" />
          ))}
        </div>
      ) : cameras.isError ? (
        <ErrorState error={cameras.error} onRetry={() => void cameras.refetch()} />
      ) : cameras.data.data.length === 0 ? (
        <EmptyState icon={Video} title="No cameras to show" description="Add cameras on the Cameras screen, or pick another location." />
      ) : (
        <>
          <div className={cn("grid gap-3", gridClass[tiles])}>
            {cameras.data.data.map((camera) => (
              <LiveTile key={camera.id} camera={camera} onExpand={() => setExpanded(camera)} />
            ))}
          </div>
          {pages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-2 text-sm">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => url.set({ page: page - 1 })}>
                Previous cameras
              </Button>
              <span className="tabular-nums">
                {page} / {pages}
              </span>
              <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => url.set({ page: page + 1 })}>
                Next cameras
              </Button>
            </div>
          )}
        </>
      )}
      <Dialog open={expanded !== null} onOpenChange={(open) => !open && setExpanded(null)}>
        <DialogContent className="max-w-[min(96vw,1400px)] p-2 sm:max-w-[min(96vw,1400px)]">
          <DialogTitle className="sr-only">{expanded?.name}</DialogTitle>
          {expanded && <LiveTile camera={expanded} large />}
        </DialogContent>
      </Dialog>
    </>
  );
}
