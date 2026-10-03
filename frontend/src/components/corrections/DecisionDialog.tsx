import { useState } from "react";

import type { CorrectionOut } from "@/api/generated/model";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useCorrectionDecision } from "@/hooks/useAttendance";
import { showError } from "@/lib/forms";

export function DecisionDialog({
  decision,
  onClose,
}: {
  decision: { correction: CorrectionOut; approve: boolean } | null;
  onClose: () => void;
}) {
  const decide = useCorrectionDecision();
  const [comment, setComment] = useState("");
  const approve = decision?.approve ?? true;
  const submit = async () => {
    if (!decision) return;
    try {
      await decide.mutateAsync({ id: decision.correction.id, approve, comment: comment.trim() || null });
      setComment("");
      onClose();
    } catch (error) {
      showError(error);
    }
  };
  return (
    <Dialog open={decision !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{approve ? "Approve correction?" : "Reject correction?"}</DialogTitle>
          <DialogDescription>
            {approve
              ? "The attendance day is recalculated with the new value, and the value is locked against later automatic changes."
              : "The attendance day stays as it is. The employee sees your comment."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="decision-comment">Comment {approve ? "(optional)" : "(recommended)"}</Label>
          <Textarea id="decision-comment" rows={3} maxLength={1000} value={comment} onChange={(e) => setComment(e.target.value)} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button variant={approve ? "default" : "destructive"} onClick={() => void submit()} disabled={decide.isPending}>
            {decide.isPending ? "Saving…" : approve ? "Approve" : "Reject"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
