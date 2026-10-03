import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import type { EventOut } from "@/api/generated/model";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Textarea } from "@/components/ui/textarea";
import { useVoidEvent } from "@/hooks/useRecognition";
import { showFormError } from "@/lib/forms";
import { reasonSchema, type ReasonValues } from "@/lib/schemas/attendance";

/** FR-28: mark a false recognition; the event is kept for tuning and attendance is rebuilt without it. */
export function VoidDialog({ event, onClose }: { event: EventOut | null; onClose: () => void }) {
  const voidEvent = useVoidEvent();
  const form = useForm<ReasonValues>({ resolver: zodResolver(reasonSchema), defaultValues: { reason: "" } });
  const submit = form.handleSubmit(async ({ reason }) => {
    if (!event) return;
    try {
      await voidEvent.mutateAsync({ id: event.id, reason });
      form.reset();
      onClose();
    } catch (error) {
      showFormError(form, error);
    }
  });
  return (
    <Dialog open={event !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Mark as wrong recognition?</DialogTitle>
          <DialogDescription>
            {event?.employee_name ?? "This event"} will no longer count towards attendance. The event stays in the log as
            voided.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={submit} className="space-y-4" noValidate>
            <FormField
              control={form.control}
              name="reason"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Reason</FormLabel>
                  <FormControl>
                    <Textarea rows={3} placeholder="For example: this is a different person" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" variant="destructive" disabled={voidEvent.isPending}>
                {voidEvent.isPending ? "Voiding…" : "Void event"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
