import type { ColumnDef } from "@tanstack/react-table";
import { UserPlus, Users } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import type { EmployeeOut, ListEmployeesParams } from "@/api/generated/model";
import { mediaUrl } from "@/api/media";
import { DataTable } from "@/components/common/DataTable";
import { EmptyState } from "@/components/common/EmptyState";
import { FilterSelect } from "@/components/common/FilterSelect";
import { PageHeader } from "@/components/common/PageHeader";
import { SearchInput } from "@/components/common/SearchInput";
import { SecureImage } from "@/components/common/SecureImage";
import { StatusBadge } from "@/components/common/StatusBadge";
import { EmployeeForm } from "@/components/employees/EmployeeForm";
import { ImportDialog } from "@/components/employees/ImportDialog";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { exportEmployees, useEmployeeMutations, useEmployees } from "@/hooks/useEmployees";
import { useDepartments } from "@/hooks/useOrganization";
import { useUrlState } from "@/hooks/useUrlState";
import { employeeStatusLabel } from "@/lib/labels";

const columns: ColumnDef<EmployeeOut>[] = [
  {
    id: "photo",
    header: "",
    meta: { className: "w-12" },
    cell: ({ row }) => (
      <SecureImage
        src={row.original.enrolled_photos ? mediaUrl.employeePhoto(row.original.id) : null}
        alt={`Photo of ${row.original.full_name}`}
        fallbackName={row.original.full_name}
        className="size-9 rounded-full"
      />
    ),
  },
  {
    accessorKey: "employee_code",
    header: "Code",
    meta: { sortKey: "employee_code", exportValue: (e) => e.employee_code },
    cell: ({ row }) => <span className="font-mono text-xs">{row.original.employee_code}</span>,
  },
  {
    accessorKey: "full_name",
    header: "Name",
    meta: { sortKey: "full_name", exportValue: (e) => e.full_name },
    cell: ({ row }) => (
      <div>
        <p className="font-medium">{row.original.full_name}</p>
        {row.original.designation && <p className="text-muted-foreground text-xs">{row.original.designation}</p>}
      </div>
    ),
  },
  {
    id: "department",
    header: "Department",
    meta: { exportValue: (e) => e.department_name ?? "" },
    cell: ({ row }) => row.original.department_name ?? "—",
  },
  {
    id: "shift",
    header: "Shift",
    meta: { exportValue: (e) => e.shift_name ?? "" },
    cell: ({ row }) => row.original.shift_name ?? "—",
  },
  {
    id: "enrollment",
    header: "Enrollment",
    meta: { exportValue: (e) => e.enrolled_photos ?? 0 },
    cell: ({ row }) => {
      const count = row.original.enrolled_photos ?? 0;
      if (count === 0) return <StatusBadge label="Not enrolled" tone="neutral" />;
      return (
        <StatusBadge
          label={`Enrolled ${count} photo${count === 1 ? "" : "s"}`}
          tone={row.original.enrollment_complete ? "ok" : "warn"}
        />
      );
    },
  },
  {
    accessorKey: "status",
    header: "Status",
    meta: { sortKey: "status", exportValue: (e) => e.status },
    cell: ({ row }) => {
      const status = employeeStatusLabel[row.original.status];
      return <StatusBadge label={status.label} tone={status.tone} />;
    },
  },
];

/** §13 screen 4. */
export function EmployeesPage() {
  const url = useUrlState();
  const navigate = useNavigate();
  const departments = useDepartments();
  const [adding, setAdding] = useState(false);
  const { create } = useEmployeeMutations();
  const enrolled = url.get("enrolled");
  const filters: ListEmployeesParams = {
    search: url.get("search") || undefined,
    department_id: url.getNumber("department_id") ?? undefined,
    status: (url.get("status") as ListEmployeesParams["status"]) ?? undefined,
    enrolled: enrolled === null ? undefined : enrolled === "true",
    sort: url.sort ?? undefined,
  };
  const query = useEmployees({ ...filters, page: url.page, page_size: url.pageSize });
  const hasFilters = Boolean(filters.search || filters.department_id || filters.status || enrolled);

  return (
    <>
      <PageHeader
        title="Employees"
        description="Employee master data and face enrollment."
        actions={
          <>
            <ImportDialog />
            <Button onClick={() => setAdding(true)}>
              <UserPlus aria-hidden /> Add employee
            </Button>
          </>
        }
      />
      <DataTable
        columns={columns}
        rows={query.data?.data}
        total={query.data?.pagination.total ?? 0}
        page={url.page}
        pageSize={url.pageSize}
        onPageChange={(page) => url.set({ page })}
        onPageSizeChange={(page_size) => url.set({ page_size })}
        sort={url.sort}
        onSortChange={(sort) => url.set({ sort })}
        isLoading={query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        getRowId={(row) => String(row.id)}
        onRowClick={(row) => navigate(`/employees/${row.id}`)}
        exportAll={() => exportEmployees(filters)}
        exportFileName="employees.csv"
        toolbar={
          <>
            <SearchInput
              value={url.get("search") ?? ""}
              onChange={(search) => url.set({ search })}
              placeholder="Search name or code"
            />
            <FilterSelect
              label="Department"
              allLabel="All departments"
              value={url.get("department_id")}
              options={(departments.data?.data ?? []).map((d) => ({ value: String(d.id), label: d.name }))}
              onChange={(department_id) => url.set({ department_id })}
            />
            <FilterSelect
              label="Status"
              allLabel="Any status"
              value={url.get("status")}
              options={[
                { value: "active", label: "Active" },
                { value: "inactive", label: "Inactive" },
              ]}
              onChange={(status) => url.set({ status })}
            />
            <FilterSelect
              label="Enrollment"
              allLabel="Any enrollment"
              value={enrolled}
              options={[
                { value: "true", label: "Enrolled" },
                { value: "false", label: "Not enrolled" },
              ]}
              onChange={(value) => url.set({ enrolled: value })}
            />
          </>
        }
        empty={
          hasFilters ? (
            <EmptyState icon={Users} title="No employees match these filters" description="Clear a filter to see more." />
          ) : (
            <EmptyState
              icon={Users}
              title="No employees yet"
              description="Add your first employee, or import a spreadsheet of all employees at once."
              action={<Button onClick={() => setAdding(true)}>Add employee</Button>}
            />
          )
        }
      />
      <Sheet open={adding} onOpenChange={setAdding}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">
          <SheetHeader>
            <SheetTitle>Add employee</SheetTitle>
            <SheetDescription>After saving, open the employee to enroll face photos.</SheetDescription>
          </SheetHeader>
          <div className="px-4 pb-4">
            <EmployeeForm
              submitLabel="Add employee"
              onCancel={() => setAdding(false)}
              onSubmit={async (payload) => {
                const result = await create.mutateAsync(payload);
                setAdding(false);
                navigate(`/employees/${result.data.id}`);
              }}
            />
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
