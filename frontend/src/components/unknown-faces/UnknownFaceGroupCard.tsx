import { UserCheck, X } from "lucide-react";
import { useId } from "react";

import type { ReviewStatus, UnknownFaceGroupOut } from "@/api/generated/model";
import { mediaUrl } from "@/api/media";
import { SecureImage } from "@/components/common/SecureImage";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDateTime } from "@/lib/format";
import { reviewStatusLabel } from "@/lib/labels";

const CAMERAS_SHOWN = 3;

function cameraSummary(group: UnknownFaceGroupOut): string {
  const names = group.camera_ids.map((id, index) => group.camera_names[index] || `Camera ${id}`);
  const shown = names.slice(0, CAMERAS_SHOWN).join(", ");
  return names.length > CAMERAS_SHOWN ? `${shown} +${names.length - CAMERAS_SHOWN} more` : shown;
}

/**
 * One card of §13 screen 9: every unknown face the API grouped as one person (Q58), with up to 8
 * sample snapshots. Assign and Dismiss act on the whole group.
 */
export function UnknownFaceGroupCard({
  group,
  status,
  timezone,
  canAssign,
  onAssign,
  onDismiss,
}: {
  group: UnknownFaceGroupOut;
  status: ReviewStatus;
  timezone: string;
  canAssign: boolean;
  onAssign: () => void;
  onDismiss: () => void;
}) {
  const titleId = useId();
  const badge = reviewStatusLabel[status];
  const single = group.face_count === 1;
  return (
    <Card role="article" aria-labelledby={titleId} className="gap-3">
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle id={titleId} className="text-sm">
          {single ? "1 sighting" : `${group.face_count} sightings`}
        </CardTitle>
        <StatusBadge label={badge.label} tone={badge.tone} />
      </CardHeader>
      <CardContent className="space-y-3">
        <ul className="grid grid-cols-4 gap-2" aria-label="Sample snapshots">
          {group.samples.map((face) => (
            <li key={face.id}>
              <SecureImage
                src={face.snapshot_available ? mediaUrl.unknownSnapshot(face.id) : null}
                alt={`Unknown face at ${face.camera_name ?? `camera ${face.camera_id}`}, ${formatDateTime(face.captured_at, timezone)}`}
                unavailableLabel="No photo"
                className="aspect-square w-full rounded-md"
              />
            </li>
          ))}
        </ul>
        {group.face_count > group.samples.length && (
          <p className="text-muted-foreground text-xs">
            Showing {group.samples.length} of {group.face_count} faces.
          </p>
        )}
        <dl className="text-muted-foreground grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
          {single ? (
            <>
              <dt>Seen</dt>
              <dd className="text-foreground">{formatDateTime(group.last_seen_at, timezone)}</dd>
            </>
          ) : (
            <>
              <dt>First seen</dt>
              <dd className="text-foreground">{formatDateTime(group.first_seen_at, timezone)}</dd>
              <dt>Last seen</dt>
              <dd className="text-foreground">{formatDateTime(group.last_seen_at, timezone)}</dd>
            </>
          )}
          <dt>{group.camera_ids.length === 1 ? "Camera" : "Cameras"}</dt>
          <dd className="text-foreground">{cameraSummary(group)}</dd>
        </dl>
        {group.pending_count > 0 && (
          <div className="flex gap-2">
            {canAssign && (
              <Button size="sm" onClick={onAssign} aria-describedby={titleId}>
                <UserCheck aria-hidden /> Assign
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={onDismiss} aria-describedby={titleId}>
              <X aria-hidden /> Dismiss
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
