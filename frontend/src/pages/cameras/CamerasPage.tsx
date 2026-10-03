import type { ColumnDef } from "@tanstack/react-table";
import { Camera, LayoutGrid, Plus, Rows3 } from "lucide-react";
import { useMemo, useState } from "react";

import type { CameraOut } from "@/api/generated/model";
import { CameraCard } from "@/components/cameras/CameraCard";
import { CameraForm } from "@/components/cameras/CameraForm";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { DataTable } from "@/components/common/DataTable";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useCameraMutations, useCameras } from "@/hooks/useCameras";
import { useLiveLoadLevels } from "@/hooks/useLiveFeed";
import { useLocationFilter } from "@/hooks/useLocationFilter";
import { useLocations } from "@/hooks/useOrganization";
import { useUrlState } from "@/hooks/useUrlState";
import { showError } from "@/lib/forms";
import { cameraModeLabel, cameraRoleLabel, cameraStatusLabel } from "@/lib/labels";
import { fetchAllPages } from "@/lib/query";
import { listCameras } from "@/api/generated/endpoints";

/** §13 screen 6. */
export function CamerasPage() {
  const url = useUrlState();
  const { locationId } = useLocationFilter();
  const locations = useLocations();
  const loadLevels = useLiveLoadLevels();
  const view = url.get("view") === "table" ? "table" : "cards";
  const params = { location_id: locationId ?? undefined, sort: url.sort ?? undefined };
  const cameras = useCameras({ ...params, page: url.page, page_size: view === "cards" ? 200 : url.pageSize });
  const { remove } = useCameraMutations();
  const [editing, setEditing] = useState<CameraOut | "new" | null>(null);
  const [deleting, setDeleting] = useState<CameraOut | null>(null);
  const locationNames = useMemo(
    () => new Map((locations.data?.data ?? []).map((l) => [l.id, l.name])),
    [locations.data],
  );

  const columns = useMemo<ColumnDef<CameraOut>[]>(
    () => [
      { accessorKey: "name", header: "Name", meta: { sortKey: "name", exportValue: (c) => c.name } },
      {
        id: "status",
        header: "Status",
        meta: { exportValue: (c) => c.status },
        cell: ({ row }) => {
          const status = cameraStatusLabel[row.original.status];
          return <StatusBadge label={status.label} tone={status.tone} />;
        },
      },
      {
        id: "mode",
        header: "Mode",
        meta: { exportValue: (c) => c.runtime?.mode ?? "" },
        cell: ({ row }) => {
          const mode = row.original.runtime ? cameraModeLabel[row.original.runtime.mode] : null;
          return mode ? <StatusBadge label={mode.label} tone={mode.tone} /> : "—";
        },
      },
      {
        id: "fps",
        header: "FPS",
        meta: { exportValue: (c) => c.runtime?.fps_actual ?? "" },
        cell: ({ row }) =>
          row.original.runtime ? `${row.original.runtime.fps_actual.toFixed(1)} / ${row.original.runtime.fps_target}` : "—",
      },
      {
        id: "node",
        header: "Engine node",
        meta: { exportValue: (c) => c.engine_node },
        cell: ({ row }) => {
          const level = loadLevels[row.original.engine_node]?.level;
          return `${row.original.engine_node}${level ? ` · level ${level}` : ""}`;
        },
      },
      {
        id: "location",
        header: "Location",
        meta: { exportValue: (c) => locationNames.get(c.location_id) ?? "" },
        cell: ({ row }) => locationNames.get(row.original.location_id) ?? "—",
      },
      {
        id: "role",
        header: "Role",
        meta: { exportValue: (c) => c.role },
        cell: ({ row }) => cameraRoleLabel[row.original.role],
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button variant="ghost" size="sm" onClick={() => setEditing(row.original)}>
              Edit
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setDeleting(row.original)}>
              Delete
            </Button>
          </div>
        ),
      },
    ],
    [loadLevels, locationNames],
  );

  const empty = (
    <EmptyState
      icon={Camera}
      title="No cameras yet"
      description="Add your first camera with its RTSP stream; FaceTrack tests it and shows a snapshot."
      action={<Button onClick={() => setEditing("new")}>Add your first camera</Button>}
    />
  );

  return (
    <>
      <PageHeader
        title="Cameras"
        description="Streams, health and recognition settings per camera."
        actions={
          <>
            <ToggleGroup
              type="single"
              variant="outline"
              value={view}
              onValueChange={(value) => value && url.set({ view: value === "table" ? "table" : null })}
              aria-label="View"
            >
              <ToggleGroupItem value="cards" aria-label="Card view">
                <LayoutGrid />
              </ToggleGroupItem>
              <ToggleGroupItem value="table" aria-label="Table view">
                <Rows3 />
              </ToggleGroupItem>
            </ToggleGroup>
            <Button onClick={() => setEditing("new")}>
              <Plus aria-hidden /> Add camera
            </Button>
          </>
        }
      />
      {view === "table" ? (
        <DataTable
          columns={columns}
          rows={cameras.data?.data}
          total={cameras.data?.pagination.total ?? 0}
          page={url.page}
          pageSize={url.pageSize}
          onPageChange={(page) => url.set({ page })}
          onPageSizeChange={(page_size) => url.set({ page_size })}
          sort={url.sort}
          onSortChange={(sort) => url.set({ sort })}
          isLoading={cameras.isPending}
          error={cameras.error}
          onRetry={() => void cameras.refetch()}
          getRowId={(row) => String(row.id)}
          exportAll={() => fetchAllPages((page, page_size) => listCameras({ ...params, page, page_size }))}
          exportFileName="cameras.csv"
          empty={empty}
        />
      ) : cameras.isPending ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-52" />
          ))}
        </div>
      ) : cameras.isError ? (
        <ErrorState error={cameras.error} onRetry={() => void cameras.refetch()} />
      ) : cameras.data.data.length === 0 ? (
        empty
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {cameras.data.data.map((camera) => (
            <CameraCard
              key={camera.id}
              camera={camera}
              locationName={locationNames.get(camera.location_id) ?? "—"}
              nodeLevel={loadLevels[camera.engine_node]?.level}
              onEdit={() => setEditing(camera)}
              onDelete={() => setDeleting(camera)}
            />
          ))}
        </div>
      )}

      <Sheet open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">
          <SheetHeader>
            <SheetTitle>{editing === "new" ? "Add camera" : `Edit ${editing?.name ?? "camera"}`}</SheetTitle>
            <SheetDescription>
              The engine picks up changes within seconds. Draw the ROI on the snapshot to ignore areas without faces.
            </SheetDescription>
          </SheetHeader>
          <div className="px-4">
            {editing !== null && (
              <CameraForm
                key={editing === "new" ? "new" : editing.id}
                camera={editing === "new" ? undefined : editing}
                onSaved={() => undefined}
              />
            )}
          </div>
        </SheetContent>
      </Sheet>

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete ${deleting?.name ?? "camera"}?`}
        description="The engine stops processing this camera. Past events stay in the event log."
        confirmLabel="Delete camera"
        pending={remove.isPending}
        onConfirm={async () => {
          if (!deleting) return;
          try {
            await remove.mutateAsync(deleting.id);
            setDeleting(null);
          } catch (error) {
            showError(error);
          }
        }}
      />
    </>
  );
}
