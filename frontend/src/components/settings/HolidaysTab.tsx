import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";

import type { HolidayOut } from "@/api/generated/model";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { CrudCard } from "@/components/settings/CrudCard";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useHolidayMutations, useHolidays, useLocations } from "@/hooks/useOrganization";
import { formatDate } from "@/lib/format";
import { showError, showFormError } from "@/lib/forms";
import { holidaySchema, type HolidayValues } from "@/lib/schemas/organization";

export function HolidaysTab() {
  const [year, setYear] = useState(new Date().getFullYear());
  const holidays = useHolidays({ date_from: `${year}-01-01`, date_to: `${year}-12-31`, sort: "date" });
  const locations = useLocations();
  const { create, update, remove } = useHolidayMutations();
  const [editing, setEditing] = useState<HolidayOut | null | undefined>(undefined);
  const [deleting, setDeleting] = useState<HolidayOut | null>(null);
  const locationName = new Map((locations.data?.data ?? []).map((l) => [l.id, l.name]));
  const form = useForm<HolidayValues>({
    resolver: zodResolver(holidaySchema),
    values: {
      location_id: editing ? String(editing.location_id) : String(locations.data?.data[0]?.id ?? ""),
      date: editing?.date ?? "",
      name: editing?.name ?? "",
    },
  });
  const submit = form.handleSubmit(async (values) => {
    try {
      if (editing) await update.mutateAsync({ id: editing.id, body: { date: values.date, name: values.name } });
      else await create.mutateAsync({ location_id: Number(values.location_id), date: values.date, name: values.name });
      setEditing(undefined);
    } catch (error) {
      showFormError(form, error);
    }
  });
  return (
    <>
      <CrudCard
        title={`Holidays ${year}`}
        description="Holidays per location. Attendance on a holiday is recorded but the day stays Holiday."
        rows={holidays.data?.data}
        columns={[
          { header: "Date", cell: (h) => formatDate(h.date) },
          { header: "Name", cell: (h) => h.name },
          { header: "Location", cell: (h) => locationName.get(h.location_id) ?? "—" },
        ]}
        isLoading={holidays.isPending}
        error={holidays.error}
        onRetry={() => void holidays.refetch()}
        addLabel="Add holiday"
        emptyText="No holidays this year."
        onAdd={() => setEditing(null)}
        onEdit={setEditing}
        onDelete={setDeleting}
        toolbar={
          <div className="flex items-center gap-1">
            <Button variant="outline" size="sm" onClick={() => setYear(year - 1)} aria-label="Previous year">
              {year - 1}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setYear(year + 1)} aria-label="Next year">
              {year + 1}
            </Button>
          </div>
        }
      />
      <Dialog open={editing !== undefined} onOpenChange={(open) => !open && setEditing(undefined)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? "Edit holiday" : "Add holiday"}</DialogTitle>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={submit} className="space-y-4" noValidate>
              <FormField
                control={form.control}
                name="location_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Location</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange} disabled={Boolean(editing)}>
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="Choose a location" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {(locations.data?.data ?? []).map((l) => (
                          <SelectItem key={l.id} value={String(l.id)}>
                            {l.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Date</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <DialogFooter>
                <Button type="submit" disabled={form.formState.isSubmitting}>
                  Save
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete holiday ${deleting?.name ?? ""}?`}
        description="Attendance for that date is recalculated; employees without a check-in become Absent."
        confirmLabel="Delete holiday"
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
