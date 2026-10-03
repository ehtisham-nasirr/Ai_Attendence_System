import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";

import type { UserOut, UserRole } from "@/api/generated/model";
import { EmployeeCombobox } from "@/components/common/EmployeeCombobox";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useUserMutations } from "@/hooks/useUsers";
import { showFormError } from "@/lib/forms";
import { roleLabel } from "@/lib/labels";
import { userSchema, type UserValues } from "@/lib/schemas/user";

export function UserDialog({ user, open, onClose }: { user: UserOut | null; open: boolean; onClose: () => void }) {
  const { create, update } = useUserMutations();
  const isNew = user === null;
  const form = useForm<UserValues>({
    resolver: zodResolver(userSchema(isNew)),
    values: {
      name: user?.name ?? "",
      username: user?.username ?? "",
      email: user?.email ?? "",
      role: user?.role ?? "hr_admin",
      auth_provider: user?.auth_provider ?? "local",
      employee_id: user?.employee_id ?? null,
      employee_label: user?.employee_id ? `Employee #${user.employee_id}` : "",
      password: "",
      is_active: user?.is_active ?? true,
    },
  });
  const [role, provider, employeeId, employeeLabel] = useWatch({
    control: form.control,
    name: ["role", "auth_provider", "employee_id", "employee_label"],
  });

  const submit = form.handleSubmit(async (values) => {
    try {
      if (isNew) {
        await create.mutateAsync({
          name: values.name,
          username: values.username,
          email: values.email,
          role: values.role,
          auth_provider: values.auth_provider,
          employee_id: values.employee_id,
          password: values.auth_provider === "local" ? values.password : null,
        });
      } else {
        await update.mutateAsync({
          id: user.id,
          body: {
            name: values.name,
            email: values.email,
            role: values.role,
            employee_id: values.employee_id,
            is_active: values.is_active,
            ...(values.password ? { password: values.password } : {}),
          },
        });
      }
      onClose();
    } catch (error) {
      showFormError(form, error);
    }
  });

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isNew ? "Add user" : `Edit ${user.name}`}</DialogTitle>
          <DialogDescription>Changing the role, password or status signs the user out everywhere.</DialogDescription>
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
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="username"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Username</FormLabel>
                    <FormControl>
                      <Input {...field} disabled={!isNew} />
                    </FormControl>
                    <FormDescription>For Active Directory, the sAMAccountName.</FormDescription>
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
            </div>
            <FormField
              control={form.control}
              name="role"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Role</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {(Object.keys(roleLabel) as UserRole[]).map((value) => (
                        <SelectItem key={value} value={value}>
                          {roleLabel[value]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {role === "department_manager" && (
                    <FormDescription>Assign the department to this manager on the Organization tab.</FormDescription>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />
            {(role === "employee" || employeeId !== null) && (
              <FormField
                control={form.control}
                name="employee_id"
                render={() => (
                  <FormItem>
                    <FormLabel>Linked employee</FormLabel>
                    <EmployeeCombobox
                      value={employeeId ? { id: employeeId, label: employeeLabel } : null}
                      onChange={(option) => {
                        form.setValue("employee_id", option?.id ?? null, { shouldValidate: true });
                        form.setValue("employee_label", option?.label ?? "");
                      }}
                    />
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}
            {isNew && (
              <FormField
                control={form.control}
                name="auth_provider"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Sign-in</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="local">FaceTrack password</SelectItem>
                        <SelectItem value="ldap">Active Directory</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}
            {provider === "local" && (
              <FormField
                control={form.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{isNew ? "First password" : "New password (optional)"}</FormLabel>
                    <FormControl>
                      <Input type="password" autoComplete="new-password" {...field} />
                    </FormControl>
                    <FormDescription>At least 10 characters with a letter and a digit.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}
            {!isNew && (
              <FormField
                control={form.control}
                name="is_active"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between gap-2">
                    <FormLabel>Account active</FormLabel>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />
            )}
            <DialogFooter>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {isNew ? "Add user" : "Save"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
