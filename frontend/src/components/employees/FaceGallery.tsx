import { ImageOff, Trash2 } from "lucide-react";
import { useState } from "react";

import { mediaUrl } from "@/api/media";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { SecureImage } from "@/components/common/SecureImage";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useTimezone } from "@/hooks/useAuth";
import { useFaceMutations, useFaces } from "@/hooks/useEmployees";
import { formatDateTime, formatPercent } from "@/lib/format";
import { showError } from "@/lib/forms";

/** §13 screen 5, Face gallery tab: enrolled photos with quality score and delete. */
export function FaceGallery({ employeeId, onEnroll }: { employeeId: number; onEnroll: () => void }) {
  const timezone = useTimezone();
  const faces = useFaces(employeeId);
  const { remove } = useFaceMutations(employeeId);
  const [pendingDelete, setPendingDelete] = useState<number | null>(null);

  if (faces.isPending) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="aspect-square" />
        ))}
      </div>
    );
  }
  if (faces.isError) return <ErrorState error={faces.error} onRetry={() => void faces.refetch()} />;
  const items = faces.data.data;
  if (items.length === 0) {
    return (
      <EmptyState
        icon={ImageOff}
        title="No face photos yet"
        description="Enroll 3 to 10 clear, front-facing photos so this employee can be recognised."
        action={<Button onClick={onEnroll}>Enroll faces</Button>}
      />
    );
  }
  return (
    <>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        {items.map((face) => (
          <li key={face.id} className="bg-card overflow-hidden rounded-lg border">
            <SecureImage
              src={mediaUrl.face(employeeId, face.id)}
              alt={`Enrolled face ${face.id}`}
              className="aspect-square w-full"
            />
            <div className="flex items-center justify-between gap-1 p-2">
              <div className="text-xs">
                <p className="font-medium">Quality {formatPercent(face.quality_score)}</p>
                <p className="text-muted-foreground">
                  {face.source === "webcam" ? "Webcam" : face.source === "review" ? "From review" : "Upload"} ·{" "}
                  {formatDateTime(face.created_at, timezone)}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="size-8"
                aria-label={`Delete face photo ${face.id}`}
                onClick={() => setPendingDelete(face.id)}
              >
                <Trash2 />
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Delete this face photo?"
        description="The photo and its embedding are deleted permanently and removed from recognition."
        confirmLabel="Delete photo"
        pending={remove.isPending}
        onConfirm={async () => {
          if (pendingDelete === null) return;
          try {
            await remove.mutateAsync(pendingDelete);
            setPendingDelete(null);
          } catch (error) {
            showError(error);
          }
        }}
      />
    </>
  );
}
