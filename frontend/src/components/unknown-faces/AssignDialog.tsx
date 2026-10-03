import { useState } from "react";

import type { UnknownFaceOut } from "@/api/generated/model";
import { mediaUrl } from "@/api/media";
import { EmployeeCombobox, type EmployeeOption } from "@/components/common/EmployeeCombobox";
import { SecureImage } from "@/components/common/SecureImage";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { useTimezone } from "@/hooks/useAuth";
import { useUnknownFaceActions } from "@/hooks/useRecognition";
import { formatDateTime } from "@/lib/format";
import { showError } from "@/lib/forms";

/** FR-27: assign to an employee (creates their attendance sighting); optionally add to the gallery. */
export function AssignDialog({ faces, onClose }: { faces: UnknownFaceOut[]; onClose: () => void }) {
  const timezone = useTimezone();
  const { assign } = useUnknownFaceActions();
  const [employee, setEmployee] = useState<EmployeeOption | null>(null);
  const [addToGallery, setAddToGallery] = useState(false);
  const [progress, setProgress] = useState(0);

  const submit = async () => {
    if (!employee) return;
    try {
      // Each face is its own sighting; the backend recomputes the day once per assignment.
      for (const [index, face] of faces.entries()) {
        await assign.mutateAsync({ id: face.id, employeeId: employee.id, addToGallery: addToGallery && index === 0 });
        setProgress(index + 1);
      }
      onClose();
    } catch (error) {
      showError(error);
    }
  };

  return (
    <Dialog open={faces.length > 0} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Assign {faces.length === 1 ? "this face" : `${faces.length} faces`} to an employee</DialogTitle>
          <DialogDescription>Each sighting is added to the employee's attendance for its day.</DialogDescription>
        </DialogHeader>
        <ul className="flex flex-wrap gap-2">
          {faces.slice(0, 8).map((face) => (
            <li key={face.id} className="space-y-1">
              <SecureImage src={face.snapshot_available ? mediaUrl.unknownSnapshot(face.id) : null} alt="Unknown face" className="size-16 rounded-md" />
              <p className="text-muted-foreground text-[10px]">{formatDateTime(face.captured_at, timezone)}</p>
            </li>
          ))}
          {faces.length > 8 && <li className="text-muted-foreground self-center text-sm">+{faces.length - 8} more</li>}
        </ul>
        <div className="space-y-2">
          <Label htmlFor="assign-employee">Employee</Label>
          <EmployeeCombobox id="assign-employee" value={employee} onChange={setEmployee} />
        </div>
        <div className="flex items-start gap-2">
          <Checkbox id="add-to-gallery" checked={addToGallery} onCheckedChange={(checked) => setAddToGallery(checked === true)} />
          <Label htmlFor="add-to-gallery" className="leading-snug font-normal">
            Add the first snapshot to the employee's face gallery (checked for quality first; needs signed consent)
          </Label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => void submit()} disabled={!employee || assign.isPending}>
            {assign.isPending ? `Assigning ${progress + 1} of ${faces.length}…` : "Assign"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
