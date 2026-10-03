import { ScanFace, UserCheck, X } from "lucide-react";
import { useMemo, useState } from "react";

import type { ReviewStatus, UnknownFaceOut } from "@/api/generated/model";
import { mediaUrl } from "@/api/media";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { FilterSelect } from "@/components/common/FilterSelect";
import { PageHeader } from "@/components/common/PageHeader";
import { SecureImage } from "@/components/common/SecureImage";
import { StatusBadge } from "@/components/common/StatusBadge";
import { AssignDialog } from "@/components/unknown-faces/AssignDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth, useTimezone } from "@/hooks/useAuth";
import { useCameras } from "@/hooks/useCameras";
import { useUnknownFaceActions, useUnknownFaces } from "@/hooks/useRecognition";
import { useUrlState } from "@/hooks/useUrlState";
import { formatDateTime } from "@/lib/format";
import { showError } from "@/lib/forms";
import { reviewStatusLabel } from "@/lib/labels";
import { Permission } from "@/lib/permissions";

const PAGE_SIZE = 60;

/** §13 screen 9: unknown snapshots grouped by similarity; assign or dismiss. */
export function UnknownFacesPage() {
  const { can } = useAuth();
  const timezone = useTimezone();
  const url = useUrlState();
  const canAssign = can(Permission.unknownFacesAssign);
  const reviewStatus = (url.get("review_status") ?? "pending") as ReviewStatus;
  const cameraId = url.getNumber("camera_id");
  const query = useUnknownFaces({
    review_status: reviewStatus,
    camera_id: cameraId ?? undefined,
    page: url.page,
    page_size: PAGE_SIZE,
  });
  const cameras = useCameras({ page: 1, page_size: 200 }, false);
  const { dismiss } = useUnknownFaceActions();
  const [assigning, setAssigning] = useState<UnknownFaceOut[]>([]);
  const [dismissing, setDismissing] = useState<UnknownFaceOut[]>([]);

  const groups = useMemo(() => {
    const byGroup = new Map<string, UnknownFaceOut[]>();
    for (const face of query.data?.data ?? []) {
      const key = face.group_id !== null && face.group_id !== undefined ? `g${face.group_id}` : `f${face.id}`;
      byGroup.set(key, [...(byGroup.get(key) ?? []), face]);
    }
    return [...byGroup.values()].sort((a, b) => b.length - a.length);
  }, [query.data]);
  const total = query.data?.pagination.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <>
      <PageHeader
        title="Unknown faces"
        description="Faces the engine could not match. Similar faces are grouped so one decision covers them."
        actions={
          <div className="flex flex-wrap gap-2">
            <FilterSelect
              label="Review status"
              allLabel="Pending"
              value={reviewStatus === "pending" ? null : reviewStatus}
              options={[
                { value: "assigned", label: "Assigned" },
                { value: "dismissed", label: "Dismissed" },
              ]}
              onChange={(value) => url.set({ review_status: value })}
            />
            <FilterSelect
              label="Camera"
              allLabel="All cameras"
              value={url.get("camera_id")}
              options={(cameras.data?.data ?? []).map((c) => ({ value: String(c.id), label: c.name }))}
              onChange={(camera_id) => url.set({ camera_id })}
            />
          </div>
        }
      />
      {query.isPending ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : groups.length === 0 ? (
        <EmptyState
          icon={ScanFace}
          title={reviewStatus === "pending" ? "Nothing to review" : "No faces here"}
          description={
            reviewStatus === "pending"
              ? "New unknown faces appear here as cameras see them. Snapshots are deleted after the retention period."
              : "Change the filters to see other faces."
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {groups.map((faces) => {
            const first = faces[0];
            const status = reviewStatusLabel[first.review_status];
            return (
              <Card key={first.id} className="gap-3">
                <CardHeader className="flex flex-row items-center justify-between gap-2">
                  <CardTitle className="text-sm">
                    {faces.length > 1 ? `${faces.length} similar sightings` : "1 sighting"}
                  </CardTitle>
                  <StatusBadge label={status.label} tone={status.tone} />
                </CardHeader>
                <CardContent className="space-y-3">
                  <ul className="grid grid-cols-4 gap-2">
                    {faces.slice(0, 8).map((face) => (
                      <li key={face.id}>
                        <SecureImage
                          src={face.snapshot_available ? mediaUrl.unknownSnapshot(face.id) : null}
                          alt={`Unknown face at ${face.camera_name ?? "camera"}`}
                          className="aspect-square w-full rounded-md"
                        />
                      </li>
                    ))}
                  </ul>
                  <p className="text-muted-foreground text-xs">
                    {first.camera_name ?? `Camera ${first.camera_id}`} · {formatDateTime(first.captured_at, timezone)}
                    {faces.length > 1 && ` … ${formatDateTime(faces[faces.length - 1].captured_at, timezone)}`}
                  </p>
                  {first.review_status === "pending" && (
                    <div className="flex gap-2">
                      {canAssign && (
                        <Button size="sm" onClick={() => setAssigning(faces)}>
                          <UserCheck aria-hidden /> Assign
                        </Button>
                      )}
                      <Button size="sm" variant="outline" onClick={() => setDismissing(faces)}>
                        <X aria-hidden /> Dismiss
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
      {pages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-2 text-sm">
          <Button variant="outline" size="sm" disabled={url.page <= 1} onClick={() => url.set({ page: url.page - 1 })}>
            Previous
          </Button>
          <span className="tabular-nums">
            {url.page} / {pages}
          </span>
          <Button variant="outline" size="sm" disabled={url.page >= pages} onClick={() => url.set({ page: url.page + 1 })}>
            Next
          </Button>
        </div>
      )}
      <AssignDialog faces={assigning} onClose={() => setAssigning([])} />
      <ConfirmDialog
        open={dismissing.length > 0}
        onOpenChange={(open) => !open && setDismissing([])}
        title={`Dismiss ${dismissing.length === 1 ? "this face" : `${dismissing.length} faces`}?`}
        description="Use this for visitors or false detections. Dismissed faces are deleted with the retention period."
        confirmLabel="Dismiss"
        destructive={false}
        pending={dismiss.isPending}
        onConfirm={async () => {
          try {
            for (const face of dismissing) await dismiss.mutateAsync(face.id);
            setDismissing([]);
          } catch (error) {
            showError(error);
          }
        }}
      />
    </>
  );
}
