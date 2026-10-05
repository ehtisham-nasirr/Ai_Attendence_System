import { useId, useMemo, useState } from "react";
import { toast } from "sonner";

import { toApiError } from "@/api/client";
import type { UnknownFaceGroupOut } from "@/api/generated/model";
import { mediaUrl } from "@/api/media";
import { EmployeeCombobox, type EmployeeOption } from "@/components/common/EmployeeCombobox";
import { SecureImage } from "@/components/common/SecureImage";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { useUnknownFaceActions } from "@/hooks/useRecognition";
import { cn } from "@/lib/utils";

const FACES_PER_PAGE = 24;

/** FR-27 for a whole group card: assign every face the reviewer kept ticked; add the best ones to the gallery (Q64). */
export function AssignDialog({ group, onClose }: { group: UnknownFaceGroupOut | null; onClose: () => void }) {
  return (
    <Dialog open={group !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        {/* Keyed so every group starts with all faces ticked and nothing chosen. */}
        {group && <AssignGroupForm key={group.group_id} group={group} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

function AssignGroupForm({ group, onClose }: { group: UnknownFaceGroupOut; onClose: () => void }) {
  const formId = useId();
  const { bulk } = useUnknownFaceActions();
  const [employee, setEmployee] = useState<EmployeeOption | null>(null);
  const [addToGallery, setAddToGallery] = useState(true);
  const [excluded, setExcluded] = useState<ReadonlySet<number>>(new Set());
  const [page, setPage] = useState(0);
  const [errors, setErrors] = useState<{ employee?: string; gallery?: string }>({});

  // Snapshot availability is known only for the sample faces; other snapshots fall back on 404.
  const knownSnapshots = useMemo(
    () => new Map(group.samples.map((face) => [face.id, face.snapshot_available])),
    [group.samples],
  );
  const total = group.face_ids.length;
  const pages = Math.max(1, Math.ceil(total / FACES_PER_PAGE));
  const start = page * FACES_PER_PAGE;
  const pageIds = group.face_ids.slice(start, start + FACES_PER_PAGE);
  const selected = group.face_ids.filter((id) => !excluded.has(id));

  const setIncluded = (id: number, included: boolean) => {
    setExcluded((previous) => {
      const next = new Set(previous);
      if (included) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const submit = async () => {
    if (!employee || selected.length === 0) return;
    setErrors({});
    try {
      await bulk.mutateAsync({
        action: "assign",
        face_ids: selected,
        employee_id: employee.id,
        add_to_gallery: addToGallery,
      });
      onClose();
    } catch (error) {
      // standards/09: field errors next to their input, anything else in a toast.
      const apiError = toApiError(error);
      const { employee_id: employeeErrors, consent_signed_at: consentErrors, ...rest } = apiError.fieldErrors;
      setErrors({ employee: employeeErrors?.join(" "), gallery: consentErrors?.join(" ") });
      const other = Object.values(rest).flat();
      if (other.length > 0) toast.error(other.join(" "));
      else if (!employeeErrors && !consentErrors) toast.error(apiError.message);
    }
  };

  return (
    <>
      <DialogHeader>
        <DialogTitle>Assign {total === 1 ? "this face" : `${total} faces`} to an employee</DialogTitle>
        <DialogDescription>
          Faces are grouped by similarity, so a group can mix two people. Untick any face that is not this person.
          Each ticked face is added to the employee's attendance for its day.
        </DialogDescription>
      </DialogHeader>
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Faces in this group</legend>
        <ul className="grid grid-cols-4 gap-2 sm:grid-cols-6">
          {pageIds.map((id, offset) => {
            const position = `${start + offset + 1} of ${total}`;
            const included = !excluded.has(id);
            const checkboxId = `${formId}-face-${id}`;
            return (
              <li key={id} className="relative">
                <label htmlFor={checkboxId} className="block cursor-pointer">
                  <SecureImage
                    src={knownSnapshots.get(id) === false ? null : mediaUrl.unknownSnapshot(id)}
                    alt={`Face ${position}`}
                    unavailableLabel="No photo"
                    className={cn("aspect-square w-full rounded-md", !included && "opacity-40")}
                  />
                </label>
                <Checkbox
                  id={checkboxId}
                  checked={included}
                  onCheckedChange={(checked) => setIncluded(id, checked === true)}
                  aria-label={`Include face ${position}`}
                  className="bg-background absolute top-1 left-1"
                />
              </li>
            );
          })}
        </ul>
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <p className="text-muted-foreground" aria-live="polite">
            {selected.length} of {total} {total === 1 ? "face" : "faces"} ticked
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {excluded.size > 0 ? (
              <Button type="button" variant="ghost" size="sm" onClick={() => setExcluded(new Set())}>
                Tick all
              </Button>
            ) : (
              <Button type="button" variant="ghost" size="sm" onClick={() => setExcluded(new Set(group.face_ids))}>
                Untick all
              </Button>
            )}
            {pages > 1 && (
              <>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={page === 0}
                  onClick={() => setPage(page - 1)}
                  aria-label="Previous faces"
                >
                  Previous
                </Button>
                <span className="tabular-nums">
                  {start + 1}–{start + pageIds.length} of {total}
                </span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={page >= pages - 1}
                  onClick={() => setPage(page + 1)}
                  aria-label="Next faces"
                >
                  Next
                </Button>
              </>
            )}
          </div>
        </div>
      </fieldset>
      <div className="space-y-2">
        <Label htmlFor={`${formId}-employee`}>Employee</Label>
        <EmployeeCombobox
          id={`${formId}-employee`}
          value={employee}
          onChange={(value) => {
            setEmployee(value);
            setErrors((previous) => ({ ...previous, employee: undefined }));
          }}
        />
        {errors.employee && (
          <p role="alert" className="text-destructive text-sm">
            {errors.employee}
          </p>
        )}
      </div>
      <div className="space-y-1">
        <div className="flex items-start gap-2">
          <Checkbox
            id={`${formId}-gallery`}
            checked={addToGallery}
            onCheckedChange={(checked) => {
              setAddToGallery(checked === true);
              setErrors((previous) => ({ ...previous, gallery: undefined }));
            }}
          />
          <Label htmlFor={`${formId}-gallery`} className="leading-snug font-normal">
            Add the best ticked faces (up to 5) to the employee's gallery as assigned photos, so the cameras
            recognise them next time (faces that also look like another employee are skipped; needs signed consent)
          </Label>
        </div>
        {errors.gallery && (
          <p role="alert" className="text-destructive text-sm">
            {errors.gallery}
          </p>
        )}
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button type="button" onClick={() => void submit()} disabled={!employee || selected.length === 0 || bulk.isPending}>
          {bulk.isPending
            ? "Assigning…"
            : `Assign ${selected.length} ${selected.length === 1 ? "face" : "faces"}`}
        </Button>
      </DialogFooter>
    </>
  );
}
