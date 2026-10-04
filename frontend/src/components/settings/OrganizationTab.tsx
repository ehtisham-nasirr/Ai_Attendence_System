import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";

import type { DepartmentOut, LocationOut } from "@/api/generated/model";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { CrudCard } from "@/components/settings/CrudCard";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useDepartmentMutations, useDepartments, useLocationMutations, useLocations } from "@/hooks/useOrganization";
import { useUsers } from "@/hooks/useUsers";
import { showError, showFormError } from "@/lib/forms";
import { departmentSchema, locationSchema, type DepartmentValues, type LocationValues } from "@/lib/schemas/organization";

const NONE = "none";

function LocationDialog({ location, open, onClose }: { location: LocationOut | null; open: boolean; onClose: () => void }) {
  const { create, update } = useLocationMutations();
  const form = useForm<LocationValues>({
    resolver: zodResolver(locationSchema),
    values: { name: location?.name ?? "", address: location?.address ?? "", timezone: location?.timezone ?? "Asia/Karachi" },
  });
  const submit = form.handleSubmit(async (values) => {
    const body = { ...values, address: values.address || null };
    try {
      if (location) await update.mutateAsync({ id: location.id, body });
      else await create.mutateAsync(body);
      onClose();
    } catch (error) {
      showFormError(form, error);
    }
  });
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{location ? "Edit location" : "Add location"}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={submit} className="space-y-4" noValidate>
            {(["name", "address", "timezone"] as const).map((name) => (
              <FormField
                key={name}
                control={form.control}
                name={name}
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{name === "timezone" ? "Timezone (IANA, e.g. Asia/Karachi)" : name[0].toUpperCase() + name.slice(1)}</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            ))}
            <DialogFooter>
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

function DepartmentDialog({
  department,
  open,
  onClose,
}: {
  department: DepartmentOut | null;
  open: boolean;
  onClose: () => void;
}) {
  const { create, update } = useDepartmentMutations();
  const managers = useUsers({ role: "department_manager", page: 1, page_size: 200 }, open);
  const form = useForm<DepartmentValues>({
    resolver: zodResolver(departmentSchema),
    values: {
      name: department?.name ?? "",
      code: department?.code ?? "",
      manager_user_id: department?.manager_user_id ? String(department.manager_user_id) : NONE,
    },
  });
  const submit = form.handleSubmit(async (values) => {
    const body = {
      name: values.name,
      code: values.code,
      manager_user_id: values.manager_user_id === NONE ? null : Number(values.manager_user_id),
    };
    try {
      if (department) await update.mutateAsync({ id: department.id, body });
      else await create.mutateAsync(body);
      onClose();
    } catch (error) {
      showFormError(form, error);
    }
  });
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{department ? "Edit department" : "Add department"}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={submit} className="space-y-4" noValidate>
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
            <FormField
              control={form.control}
              name="code"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Code (used in imports)</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="manager_user_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Manager (approves this department's corrections)</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value={NONE}>No manager</SelectItem>
                      {(managers.data?.data ?? []).map((user) => (
                        <SelectItem key={user.id} value={String(user.id)}>
                          {user.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
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
  );
}

/** FR-36 locations and the department list (managers scope §4). */
export function OrganizationTab() {
  const locations = useLocations();
  const departments = useDepartments();
  const locationMutations = useLocationMutations();
  const departmentMutations = useDepartmentMutations();
  const [editingLocation, setEditingLocation] = useState<LocationOut | null | undefined>(undefined);
  const [editingDepartment, setEditingDepartment] = useState<DepartmentOut | null | undefined>(undefined);
  const [deleting, setDeleting] = useState<{ kind: "location"; row: LocationOut } | { kind: "department"; row: DepartmentOut } | null>(null);

  return (
    <div className="space-y-6">
      <CrudCard
        title="Locations"
        description="Office locations, each with its own cameras, holidays and timezone."
        rows={locations.data?.data}
        columns={[
          { header: "Name", cell: (l) => l.name },
          { header: "Timezone", cell: (l) => l.timezone },
          { header: "Address", cell: (l) => l.address ?? "—" },
        ]}
        isLoading={locations.isPending}
        error={locations.error}
        onRetry={() => void locations.refetch()}
        addLabel="Add location"
        emptyText="No locations yet. Add the first office location."
        onAdd={() => setEditingLocation(null)}
        onEdit={setEditingLocation}
        onDelete={(row) => setDeleting({ kind: "location", row })}
      />
      <CrudCard
        title="Departments"
        rows={departments.data?.data}
        columns={[
          { header: "Name", cell: (d) => d.name },
          { header: "Code", cell: (d) => <span className="tabular-nums">{d.code}</span> },
        ]}
        isLoading={departments.isPending}
        error={departments.error}
        onRetry={() => void departments.refetch()}
        addLabel="Add department"
        emptyText="No departments yet."
        onAdd={() => setEditingDepartment(null)}
        onEdit={setEditingDepartment}
        onDelete={(row) => setDeleting({ kind: "department", row })}
      />
      <LocationDialog location={editingLocation ?? null} open={editingLocation !== undefined} onClose={() => setEditingLocation(undefined)} />
      <DepartmentDialog
        department={editingDepartment ?? null}
        open={editingDepartment !== undefined}
        onClose={() => setEditingDepartment(undefined)}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete ${deleting?.row.name ?? ""}?`}
        description="Employees and cameras that reference it keep their history but lose the link."
        confirmLabel="Delete"
        pending={locationMutations.remove.isPending || departmentMutations.remove.isPending}
        onConfirm={async () => {
          if (!deleting) return;
          try {
            if (deleting.kind === "location") await locationMutations.remove.mutateAsync(deleting.row.id);
            else await departmentMutations.remove.mutateAsync(deleting.row.id);
            setDeleting(null);
          } catch (error) {
            showError(error);
          }
        }}
      />
    </div>
  );
}
