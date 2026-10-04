import { Info, ScanFace } from "lucide-react";
import { useEffect, useState } from "react";

import type { ReviewStatus, UnknownFaceGroupOut } from "@/api/generated/model";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { FilterSelect } from "@/components/common/FilterSelect";
import { PageHeader } from "@/components/common/PageHeader";
import { AssignDialog } from "@/components/unknown-faces/AssignDialog";
import { UnknownFaceGroupCard } from "@/components/unknown-faces/UnknownFaceGroupCard";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth, useTimezone } from "@/hooks/useAuth";
import { useCameras } from "@/hooks/useCameras";
import { useUnknownFaceActions, useUnknownFaceGroups } from "@/hooks/useRecognition";
import { useUrlState } from "@/hooks/useUrlState";
import { showError } from "@/lib/forms";
import { Permission } from "@/lib/permissions";

/** Groups per page; each card loads up to 8 thumbnails. */
const PAGE_SIZE = 12;

/** §13 screen 9: one card per group of similar unknown faces over the whole queue (Q58); assign or dismiss a card. */
export function UnknownFacesPage() {
  const { can } = useAuth();
  const timezone = useTimezone();
  const url = useUrlState();
  const canAssign = can(Permission.unknownFacesAssign);
  const reviewStatus = (url.get("review_status") ?? "pending") as ReviewStatus;
  const cameraId = url.getNumber("camera_id");
  const query = useUnknownFaceGroups({
    review_status: reviewStatus,
    camera_id: cameraId ?? undefined,
    page: url.page,
    page_size: PAGE_SIZE,
  });
  const cameras = useCameras({ page: 1, page_size: 200 }, false);
  const { bulk } = useUnknownFaceActions();
  const [assigning, setAssigning] = useState<UnknownFaceGroupOut | null>(null);
  const [dismissing, setDismissing] = useState<UnknownFaceGroupOut | null>(null);

  const groups = query.data?.data ?? [];
  const grouping = query.data?.grouping;
  const total = query.data?.pagination.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // A decision removes whole cards, so the current page can end up past the last one.
  const pageIsPastEnd = query.isSuccess && !query.isPlaceholderData && groups.length === 0 && url.page > 1;
  const setUrl = url.set;
  useEffect(() => {
    if (pageIsPastEnd) setUrl({ page: pages > 1 ? pages : null });
  }, [pageIsPastEnd, pages, setUrl]);

  const dismissCount = dismissing?.face_ids.length ?? 0;

  return (
    <>
      <PageHeader
        title="Unknown faces"
        description="Faces the engine could not match. Similar faces across the whole queue are grouped into one card, so one decision covers them."
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
        <>
          <div className="text-muted-foreground mb-3 space-y-1 text-sm">
            {grouping && (
              <p>
                {grouping.faces_grouped} {grouping.faces_grouped === 1 ? "face" : "faces"} in {total}{" "}
                {total === 1 ? "group" : "groups"}
              </p>
            )}
            {grouping?.truncated && (
              <p role="note" className="flex items-start gap-1.5">
                <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
                Only the newest {grouping.faces_grouped} of {grouping.faces_total} faces are grouped. Older faces
                appear here as the queue gets shorter.
              </p>
            )}
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {groups.map((group) => (
              <UnknownFaceGroupCard
                key={group.group_id}
                group={group}
                status={reviewStatus}
                timezone={timezone}
                canAssign={canAssign}
                onAssign={() => setAssigning(group)}
                onDismiss={() => setDismissing(group)}
              />
            ))}
          </div>
        </>
      )}
      {pages > 1 && (
        <nav aria-label="Pages of groups" className="mt-4 flex items-center justify-center gap-2 text-sm">
          <Button variant="outline" size="sm" disabled={url.page <= 1} onClick={() => url.set({ page: url.page - 1 })}>
            Previous
          </Button>
          <span className="tabular-nums">
            {url.page} / {pages}
          </span>
          <Button variant="outline" size="sm" disabled={url.page >= pages} onClick={() => url.set({ page: url.page + 1 })}>
            Next
          </Button>
        </nav>
      )}
      <AssignDialog group={assigning} onClose={() => setAssigning(null)} />
      <ConfirmDialog
        open={dismissing !== null}
        onOpenChange={(open) => !open && setDismissing(null)}
        title={`Dismiss ${dismissCount === 1 ? "this face" : `all ${dismissCount} faces in this group`}?`}
        description="Use this for visitors or false detections. Dismissed faces are deleted with the retention period."
        confirmLabel="Dismiss"
        destructive={false}
        pending={bulk.isPending}
        onConfirm={async () => {
          if (!dismissing) return;
          try {
            await bulk.mutateAsync({ action: "dismiss", face_ids: dismissing.face_ids });
            setDismissing(null);
          } catch (error) {
            showError(error);
          }
        }}
      />
    </>
  );
}
