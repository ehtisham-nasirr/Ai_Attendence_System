import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";

import type { AttendanceStatus } from "@/api/generated/model";
import { EmployeeCombobox, type EmployeeOption } from "@/components/common/EmployeeCombobox";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAttendanceMutations } from "@/hooks/useAttendance";
import { useTimezone } from "@/hooks/useAuth";
import { localToUtcIso, todayIn } from "@/lib/format";
import { showFormError } from "@/lib/forms";
import { attendanceStatusLabel } from "@/lib/labels";
import { nextDay } from "@/lib/month";
import { manualEntrySchema, type ManualEntryValues } from "@/lib/schemas/attendance";

const AUTO = "auto";

/** FR-25 / Q22: add attendance for an employee who has no record on that day. */
export function ManualEntryDialog({
  open,
  onOpenChange,
  defaultDate,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultDate: string;
}) {
  const timezone = useTimezone();
  const { createManual } = useAttendanceMutations();
  const [employee, setEmployee] = useState<EmployeeOption | null>(null);
  const form = useForm<ManualEntryValues>({
    resolver: zodResolver(manualEntrySchema),
    defaultValues: {
      employee_id: 0,
      work_date: defaultDate,
      check_in: "",
      check_out: "",
      check_out_next_day: false,
      status: AUTO,
      reason: "",
    },
  });

  const submit = form.handleSubmit(async (values) => {
    try {
      await createManual.mutateAsync({
        employee_id: values.employee_id,
        work_date: values.work_date,
        check_in_at: values.check_in ? localToUtcIso(values.work_date, values.check_in, timezone) : null,
        check_out_at: values.check_out
          ? localToUtcIso(values.check_out_next_day ? nextDay(values.work_date) : values.work_date, values.check_out, timezone)
          : null,
        status: values.status === AUTO ? null : (values.status as AttendanceStatus),
        reason: values.reason,
      });
      form.reset();
      setEmployee(null);
      onOpenChange(false);
    } catch (error) {
      showFormError(form, error);
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add manual attendance</DialogTitle>
          <DialogDescription>For a day with no record. To change an existing day, use Correct on its row.</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={submit} className="space-y-4" noValidate>
            <FormField
              control={form.control}
              name="employee_id"
              render={() => (
                <FormItem>
                  <FormLabel>Employee</FormLabel>
                  <EmployeeCombobox
                    value={employee}
                    onChange={(option) => {
                      setEmployee(option);
                      form.setValue("employee_id", option?.id ?? 0, { shouldValidate: true });
                    }}
                  />
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="work_date"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Work date</FormLabel>
                  <FormControl>
                    <Input type="date" max={todayIn(timezone)} {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid grid-cols-2 gap-3">
              <FormField
                control={form.control}
                name="check_in"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Check-in</FormLabel>
                    <FormControl>
                      <Input type="time" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="check_out"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Check-out</FormLabel>
                    <FormControl>
                      <Input type="time" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <FormField
              control={form.control}
              name="check_out_next_day"
              render={({ field }) => (
                <FormItem className="flex items-center gap-2">
                  <FormControl>
                    <Checkbox checked={field.value} onCheckedChange={(checked) => field.onChange(checked === true)} />
                  </FormControl>
                  <FormLabel className="font-normal">Check-out is on the next day (night shift)</FormLabel>
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="status"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Status</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value={AUTO}>Calculate from the times</SelectItem>
                      {(Object.keys(attendanceStatusLabel) as AttendanceStatus[]).map((status) => (
                        <SelectItem key={status} value={status}>
                          {attendanceStatusLabel[status].label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormDescription>Set a status only to override the attendance rules.</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="reason"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Reason</FormLabel>
                  <FormControl>
                    <Textarea rows={3} {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button type="submit" disabled={createManual.isPending}>
              {createManual.isPending ? "Saving…" : "Add entry"}
            </Button>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
