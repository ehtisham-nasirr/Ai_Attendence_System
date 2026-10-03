import { zodResolver } from "@hookform/resolvers/zod";
import { CalendarClock, Trash2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import type { ReportType } from "@/api/generated/model";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { useDepartments } from "@/hooks/useOrganization";
import { useSettings, useUpdateSettings } from "@/hooks/useSettings";
import { showError } from "@/lib/forms";
import { REPORTS, reportInfo } from "@/lib/reports";
import { reportScheduleSchema, splitRecipients, type ReportScheduleValues, type StoredSchedule } from "@/lib/schemas/report";

const KEY = "notifications.report_schedules";
const ALL = "all";
const when: Record<StoredSchedule["frequency"], string> = {
  daily: "Every day (yesterday's data)",
  weekly: "Every Monday (last week)",
  monthly: "On the 1st (last month)",
};

/** FR-32 / §13 screen 12 "schedule email": stored in the notifications settings (Admin). */
export function ScheduleDialog({ defaultType }: { defaultType: ReportType }) {
  const settings = useSettings();
  const update = useUpdateSettings();
  const departments = useDepartments();
  const [open, setOpen] = useState(false);
  const schedules = (settings.data?.data.find((item) => item.key === KEY)?.value ?? []) as StoredSchedule[];
  const departmentName = new Map((departments.data?.data ?? []).map((d) => [d.id, d.name]));
  const form = useForm<ReportScheduleValues>({
    resolver: zodResolver(reportScheduleSchema),
    defaultValues: {
      report_type: defaultType === "employee_history" ? "daily" : defaultType,
      frequency: "daily",
      time: "08:00",
      recipients: "",
      department_id: ALL,
      format: "xlsx",
    },
  });

  const save = async (next: StoredSchedule[]) => {
    try {
      await update.mutateAsync({ [KEY]: next });
      return true;
    } catch (error) {
      showError(error);
      return false;
    }
  };

  const add = form.handleSubmit(async (values) => {
    const schedule: StoredSchedule = {
      ...values,
      recipients: splitRecipients(values.recipients),
      department_id: values.department_id === ALL ? null : Number(values.department_id),
    };
    if (await save([...schedules, schedule])) form.reset({ ...form.getValues(), recipients: "" });
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">
          <CalendarClock aria-hidden /> Schedule email
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Scheduled report emails</DialogTitle>
          <DialogDescription>Reports are generated for the whole organisation or one department and sent as attachments.</DialogDescription>
        </DialogHeader>
        {schedules.length === 0 ? (
          <p className="text-muted-foreground text-sm">No scheduled reports yet.</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {schedules.map((schedule, index) => (
              <li key={index} className="flex items-start justify-between gap-2 p-3 text-sm">
                <div>
                  <p className="font-medium">
                    {reportInfo(schedule.report_type as ReportType).label} · {schedule.format.toUpperCase()}
                  </p>
                  <p className="text-muted-foreground">
                    {when[schedule.frequency]} at {schedule.time} ·{" "}
                    {schedule.department_id ? (departmentName.get(schedule.department_id) ?? "Department") : "All departments"}
                  </p>
                  <p className="text-muted-foreground">{schedule.recipients.join(", ")}</p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Remove schedule"
                  onClick={() => void save(schedules.filter((_, i) => i !== index))}
                >
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
        )}
        <Separator />
        <Form {...form}>
          <form onSubmit={add} className="grid gap-3 sm:grid-cols-2" noValidate>
            <FormField
              control={form.control}
              name="report_type"
              render={({ field }) => (
                <FormItem className="sm:col-span-2">
                  <FormLabel>Report</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {REPORTS.filter((r) => r.type !== "employee_history").map((r) => (
                        <SelectItem key={r.type} value={r.type}>
                          {r.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="frequency"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>When</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {(Object.keys(when) as StoredSchedule["frequency"][]).map((value) => (
                        <SelectItem key={value} value={value}>
                          {when[value]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="time"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Time</FormLabel>
                  <FormControl>
                    <Input type="time" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="department_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Department</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value={ALL}>All departments</SelectItem>
                      {(departments.data?.data ?? []).map((d) => (
                        <SelectItem key={d.id} value={String(d.id)}>
                          {d.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="format"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Format</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="xlsx">Excel</SelectItem>
                      <SelectItem value="pdf">PDF</SelectItem>
                    </SelectContent>
                  </Select>
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="recipients"
              render={({ field }) => (
                <FormItem className="sm:col-span-2">
                  <FormLabel>Recipients</FormLabel>
                  <FormControl>
                    <Input placeholder="hr@example.com, manager@example.com" {...field} />
                  </FormControl>
                  <FormDescription>Times use the organisation timezone (Settings › General).</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="sm:col-span-2">
              <Button type="submit" disabled={update.isPending}>
                Add schedule
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
