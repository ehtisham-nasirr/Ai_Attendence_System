import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";

import type { ShiftOut } from "@/api/generated/model";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { CrudCard } from "@/components/settings/CrudCard";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useShiftMutations, useShifts } from "@/hooks/useOrganization";
import { showError, showFormError } from "@/lib/forms";
import { WEEKDAYS } from "@/lib/month";
import { shiftSchema, type ShiftValues } from "@/lib/schemas/organization";

const hhmm = (value: string) => value.slice(0, 5);

function ShiftDialog({ shift, open, onClose }: { shift: ShiftOut | null; open: boolean; onClose: () => void }) {
  const { create, update } = useShiftMutations();
  const form = useForm<ShiftValues>({
    resolver: zodResolver(shiftSchema),
    values: {
      name: shift?.name ?? "",
      start_time: shift ? hhmm(shift.start_time) : "09:00",
      end_time: shift ? hhmm(shift.end_time) : "18:00",
      grace_in_min: shift?.grace_in_min ?? 15,
      grace_out_min: shift?.grace_out_min ?? 15,
      half_day_pct: shift?.half_day_pct ?? 50,
      is_night_shift: shift?.is_night_shift ?? false,
      weekly_offs: shift?.weekly_offs ?? [6, 7],
    },
  });
  const submit = form.handleSubmit(async (values) => {
    try {
      if (shift) await update.mutateAsync({ id: shift.id, body: values });
      else await create.mutateAsync(values);
      onClose();
    } catch (error) {
      showFormError(form, error);
    }
  });
  const number = (name: "grace_in_min" | "grace_out_min" | "half_day_pct", label: string, hint: string) => (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input type="number" value={field.value} onChange={(e) => field.onChange(Number(e.target.value))} />
          </FormControl>
          <FormDescription>{hint}</FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  );
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{shift ? "Edit shift" : "Add shift"}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2" noValidate>
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem className="sm:col-span-2">
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            {(["start_time", "end_time"] as const).map((name) => (
              <FormField
                key={name}
                control={form.control}
                name={name}
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{name === "start_time" ? "Starts" : "Ends"}</FormLabel>
                    <FormControl>
                      <Input type="time" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            ))}
            {number("grace_in_min", "Late after (minutes)", "Grace period after the start.")}
            {number("grace_out_min", "Early exit before (minutes)", "Grace period before the end.")}
            {number("half_day_pct", "Half day below (% of shift)", "Worked time below this is Half Day.")}
            <FormField
              control={form.control}
              name="is_night_shift"
              render={({ field }) => (
                <FormItem className="flex items-center justify-between gap-2 self-end">
                  <FormLabel>Night shift (ends next day)</FormLabel>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="weekly_offs"
              render={({ field }) => (
                <FormItem className="sm:col-span-2">
                  <FormLabel>Weekly off days</FormLabel>
                  <ToggleGroup
                    type="multiple"
                    variant="outline"
                    value={field.value.map(String)}
                    onValueChange={(days) => field.onChange(days.map(Number).sort())}
                  >
                    {WEEKDAYS.map((label, index) => (
                      <ToggleGroupItem key={label} value={String(index + 1)} aria-label={label}>
                        {label}
                      </ToggleGroupItem>
                    ))}
                  </ToggleGroup>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter className="sm:col-span-2">
              <Button type="submit" disabled={form.formState.isSubmitting}>
                Save
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

/** FR-21: shifts with grace periods, half-day rule, night shifts and weekly offs. */
export function ShiftsTab() {
  const shifts = useShifts();
  const { remove } = useShiftMutations();
  const [editing, setEditing] = useState<ShiftOut | null | undefined>(undefined);
  const [deleting, setDeleting] = useState<ShiftOut | null>(null);
  return (
    <>
      <CrudCard
        title="Shifts"
        description="Assigned to employees; attendance status is judged against the employee's shift."
        rows={shifts.data?.data}
        columns={[
          { header: "Name", cell: (s) => s.name },
          { header: "Hours", cell: (s) => `${hhmm(s.start_time)}–${hhmm(s.end_time)}${s.is_night_shift ? " (night)" : ""}` },
          { header: "Grace in / out", cell: (s) => `${s.grace_in_min} / ${s.grace_out_min} min` },
          { header: "Weekly off", cell: (s) => s.weekly_offs.map((d) => WEEKDAYS[d - 1]).join(", ") || "—" },
        ]}
        isLoading={shifts.isPending}
        error={shifts.error}
        onRetry={() => void shifts.refetch()}
        addLabel="Add shift"
        emptyText="No shifts yet. Without a shift, employees are never marked absent."
        onAdd={() => setEditing(null)}
        onEdit={setEditing}
        onDelete={setDeleting}
      />
      <ShiftDialog shift={editing ?? null} open={editing !== undefined} onClose={() => setEditing(undefined)} />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete shift ${deleting?.name ?? ""}?`}
        description="Employees on this shift keep past attendance; assign them another shift."
        confirmLabel="Delete shift"
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
