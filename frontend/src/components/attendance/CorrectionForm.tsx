import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";

import type { AttendanceDayOut, AttendanceStatus } from "@/api/generated/model";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAttendanceMutations } from "@/hooks/useAttendance";
import { useTimezone } from "@/hooks/useAuth";
import { localToUtcIso, todayIn } from "@/lib/format";
import { showFormError } from "@/lib/forms";
import { attendanceStatusLabel, correctionFieldLabel } from "@/lib/labels";
import { correctionSchema, type CorrectionFormValues } from "@/lib/schemas/attendance";

/**
 * FR-25/FR-26: HR, managers and admins apply the change directly; employees send a request that their
 * manager or HR approves (ADR-0004). The API decides which, from the user's role.
 */
export function CorrectionForm({
  day,
  appliesDirectly,
  onDone,
}: {
  day: AttendanceDayOut;
  appliesDirectly: boolean;
  onDone: () => void;
}) {
  const timezone = useTimezone();
  const { correct } = useAttendanceMutations();
  const form = useForm<CorrectionFormValues>({
    resolver: zodResolver(correctionSchema),
    defaultValues: { field: "check_in_at", date: day.work_date, time: "", status: "", reason: "" },
  });
  const field = useWatch({ control: form.control, name: "field" });

  const submit = form.handleSubmit(async (values) => {
    const newValue =
      values.field === "status" ? values.status : localToUtcIso(values.date, values.time, timezone);
    try {
      await correct.mutateAsync({ dayId: day.id, body: { field: values.field, new_value: newValue, reason: values.reason } });
      onDone();
    } catch (error) {
      const apiError = showFormError(form, error);
      if (apiError.fieldErrors.new_value) {
        form.setError(values.field === "status" ? "status" : "time", { message: apiError.fieldErrors.new_value.join(" ") });
      }
    }
  });

  return (
    <Form {...form}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <FormField
          control={form.control}
          name="field"
          render={({ field: input }) => (
            <FormItem>
              <FormLabel>What is wrong?</FormLabel>
              <Select value={input.value} onValueChange={input.onChange}>
                <FormControl>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {(["check_in_at", "check_out_at", "status"] as const).map((value) => (
                    <SelectItem key={value} value={value}>
                      {correctionFieldLabel[value]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />
        {field === "status" ? (
          <FormField
            control={form.control}
            name="status"
            render={({ field: input }) => (
              <FormItem>
                <FormLabel>Correct status</FormLabel>
                <Select value={input.value} onValueChange={input.onChange}>
                  <FormControl>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Choose a status" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {(Object.keys(attendanceStatusLabel) as AttendanceStatus[]).map((status) => (
                      <SelectItem key={status} value={status}>
                        {attendanceStatusLabel[status].label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <FormField
              control={form.control}
              name="date"
              render={({ field: input }) => (
                <FormItem>
                  <FormLabel>Date</FormLabel>
                  <FormControl>
                    <Input type="date" max={todayIn(timezone)} {...input} />
                  </FormControl>
                  <FormDescription>Next day for night shifts.</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="time"
              render={({ field: input }) => (
                <FormItem>
                  <FormLabel>Time</FormLabel>
                  <FormControl>
                    <Input type="time" {...input} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        )}
        <FormField
          control={form.control}
          name="reason"
          render={({ field: input }) => (
            <FormItem>
              <FormLabel>Reason</FormLabel>
              <FormControl>
                <Textarea rows={3} placeholder="For example: camera was offline at the main entrance" {...input} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit" disabled={correct.isPending}>
          {correct.isPending ? "Saving…" : appliesDirectly ? "Apply correction" : "Send request"}
        </Button>
      </form>
    </Form>
  );
}
