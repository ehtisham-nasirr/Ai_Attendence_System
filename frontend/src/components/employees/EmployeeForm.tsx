import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import type { EmployeeCreate, EmployeeOut } from "@/api/generated/model";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useDepartments, useLocations, useShifts } from "@/hooks/useOrganization";
import { useTimezone } from "@/hooks/useAuth";
import { localToUtcIso, todayIn } from "@/lib/format";
import { showFormError } from "@/lib/forms";
import { employeeSchema, type EmployeeFormValues } from "@/lib/schemas/employee";

const NONE = "none";

function toValues(employee: EmployeeOut | undefined, timezone: string): EmployeeFormValues {
  return {
    employee_code: employee?.employee_code ?? "",
    full_name: employee?.full_name ?? "",
    department_id: employee?.department_id ? String(employee.department_id) : NONE,
    designation: employee?.designation ?? "",
    shift_id: employee?.shift_id ? String(employee.shift_id) : NONE,
    location_id: employee?.location_id ? String(employee.location_id) : NONE,
    email: employee?.email ?? "",
    phone: employee?.phone ?? "",
    status: employee?.status ?? "active",
    consent_date: employee?.consent_signed_at ? todayIn(timezone, new Date(employee.consent_signed_at)) : "",
    hr_external_id: employee?.hr_external_id ?? "",
  };
}

const idOrNull = (value: string) => (value === NONE ? null : Number(value));
const textOrNull = (value: string) => (value.trim() === "" ? null : value.trim());

function toPayload(values: EmployeeFormValues, timezone: string): EmployeeCreate {
  return {
    employee_code: values.employee_code.trim(),
    full_name: values.full_name.trim(),
    department_id: idOrNull(values.department_id),
    designation: textOrNull(values.designation),
    shift_id: idOrNull(values.shift_id),
    location_id: idOrNull(values.location_id),
    email: textOrNull(values.email),
    phone: textOrNull(values.phone),
    status: values.status,
    consent_signed_at: values.consent_date ? localToUtcIso(values.consent_date, "12:00", timezone) : null,
    hr_external_id: textOrNull(values.hr_external_id),
  };
}

function RefSelect({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  options: { id: number; name: string }[];
  placeholder: string;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <FormControl>
        <SelectTrigger className="w-full">
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
      </FormControl>
      <SelectContent>
        <SelectItem value={NONE}>{placeholder}</SelectItem>
        {options.map((option) => (
          <SelectItem key={option.id} value={String(option.id)}>
            {option.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** Create (code editable) or edit an employee (FR-7). */
export function EmployeeForm({
  employee,
  onSubmit,
  submitLabel,
  onCancel,
}: {
  employee?: EmployeeOut;
  onSubmit: (payload: EmployeeCreate) => Promise<unknown>;
  submitLabel: string;
  onCancel?: () => void;
}) {
  const timezone = useTimezone();
  const departments = useDepartments();
  const shifts = useShifts();
  const locations = useLocations();
  const form = useForm<EmployeeFormValues>({
    resolver: zodResolver(employeeSchema),
    defaultValues: toValues(employee, timezone),
  });

  const submit = form.handleSubmit(async (values) => {
    try {
      await onSubmit(toPayload(values, timezone));
      if (!employee) form.reset(toValues(undefined, timezone));
    } catch (error) {
      showFormError(form, error);
    }
  });

  return (
    <Form {...form}>
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2" noValidate>
        <FormField
          control={form.control}
          name="employee_code"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Employee code</FormLabel>
              <FormControl>
                <Input {...field} disabled={Boolean(employee)} />
              </FormControl>
              {employee && <FormDescription>The code cannot be changed.</FormDescription>}
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="full_name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Full name</FormLabel>
              <FormControl>
                <Input {...field} />
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
              <RefSelect
                value={field.value}
                onChange={field.onChange}
                options={departments.data?.data ?? []}
                placeholder="No department"
              />
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="designation"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Designation</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="shift_id"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Shift</FormLabel>
              <RefSelect value={field.value} onChange={field.onChange} options={shifts.data?.data ?? []} placeholder="No shift" />
              <FormDescription>Without a shift the employee is never marked absent.</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="location_id"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Location</FormLabel>
              <RefSelect
                value={field.value}
                onChange={field.onChange}
                options={locations.data?.data ?? []}
                placeholder="No location"
              />
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Email</FormLabel>
              <FormControl>
                <Input type="email" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="phone"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Phone</FormLabel>
              <FormControl>
                <Input type="tel" {...field} />
              </FormControl>
              <FormMessage />
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
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="inactive">Inactive (recognition stops immediately)</SelectItem>
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="consent_date"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Biometric consent signed on</FormLabel>
              <FormControl>
                <Input type="date" max={todayIn(timezone)} {...field} />
              </FormControl>
              <FormDescription>Face enrollment is blocked until the signed consent form is recorded.</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="hr_external_id"
          render={({ field }) => (
            <FormItem>
              <FormLabel>HR system ID</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <div className="flex justify-end gap-2 sm:col-span-2">
          {onCancel && (
            <Button type="button" variant="outline" onClick={onCancel}>
              Cancel
            </Button>
          )}
          <Button type="submit" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? "Saving…" : submitLabel}
          </Button>
        </div>
      </form>
    </Form>
  );
}
