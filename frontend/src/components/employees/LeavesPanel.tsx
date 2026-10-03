import { zodResolver } from "@hookform/resolvers/zod";
import { CalendarOff, Trash2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState } from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useLeaveMutations, useLeaves } from "@/hooks/useEmployees";
import { formatDate } from "@/lib/format";
import { showError, showFormError } from "@/lib/forms";
import { leaveSchema, type LeaveFormValues } from "@/lib/schemas/employee";

/** Approved leave for one employee (FR-24, Q30): imported from HR or entered here. */
export function LeavesPanel({ employeeId }: { employeeId: number }) {
  const leaves = useLeaves({ employee_id: employeeId, page: 1, page_size: 100, sort: "-from_date" });
  const { create, remove } = useLeaveMutations();
  const [pendingDelete, setPendingDelete] = useState<number | null>(null);
  const form = useForm<LeaveFormValues>({
    resolver: zodResolver(leaveSchema),
    defaultValues: { from_date: "", to_date: "", type: "Annual" },
  });

  const submit = form.handleSubmit(async (values) => {
    try {
      await create.mutateAsync({ employee_id: employeeId, ...values });
      form.reset({ from_date: "", to_date: "", type: values.type });
    } catch (error) {
      showFormError(form, error);
    }
  });

  return (
    <div className="space-y-6">
      <Form {...form}>
        <form onSubmit={submit} className="grid items-end gap-3 sm:grid-cols-4" noValidate>
          <FormField
            control={form.control}
            name="from_date"
            render={({ field }) => (
              <FormItem>
                <FormLabel>From</FormLabel>
                <FormControl>
                  <Input type="date" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="to_date"
            render={({ field }) => (
              <FormItem>
                <FormLabel>To</FormLabel>
                <FormControl>
                  <Input type="date" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="type"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Type</FormLabel>
                <FormControl>
                  <Input {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <Button type="submit" disabled={create.isPending}>
            Add leave
          </Button>
        </form>
      </Form>
      {leaves.isPending ? (
        <Skeleton className="h-24" />
      ) : (leaves.data?.data.length ?? 0) === 0 ? (
        <EmptyState icon={CalendarOff} title="No leave recorded" description="Approved leave days are shown as On leave, not Absent." />
      ) : (
        <ul className="divide-y rounded-lg border">
          {leaves.data?.data.map((leave) => (
            <li key={leave.id} className="flex items-center justify-between gap-3 p-3 text-sm">
              <div>
                <p className="font-medium">
                  {formatDate(leave.from_date)} – {formatDate(leave.to_date)}
                </p>
                <p className="text-muted-foreground">
                  {leave.type} · {leave.source === "hr" ? "From HR system" : "Entered manually"}
                </p>
              </div>
              {leave.source === "manual" && (
                <Button variant="ghost" size="icon" aria-label="Remove leave" onClick={() => setPendingDelete(leave.id)}>
                  <Trash2 />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Remove this leave?"
        description="Attendance for these days is recalculated; days without a check-in become Absent at day close."
        confirmLabel="Remove leave"
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
    </div>
  );
}
