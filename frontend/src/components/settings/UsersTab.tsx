import type { ColumnDef } from "@tanstack/react-table";
import { LockOpen, Pencil, Trash2, UserPlus, Users } from "lucide-react";
import { useMemo, useState } from "react";

import type { UserOut, UserRole } from "@/api/generated/model";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { DataTable } from "@/components/common/DataTable";
import { EmptyState } from "@/components/common/EmptyState";
import { FilterSelect } from "@/components/common/FilterSelect";
import { SearchInput } from "@/components/common/SearchInput";
import { StatusBadge } from "@/components/common/StatusBadge";
import { UserDialog } from "@/components/settings/UserDialog";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";
import { useUserMutations, useUsers } from "@/hooks/useUsers";
import { formatDateTime } from "@/lib/format";
import { showError } from "@/lib/forms";
import { roleLabel } from "@/lib/labels";
import { fetchAllPages } from "@/lib/query";
import { listUsers } from "@/api/generated/endpoints";

/** §4 roles: portal accounts (Super Admin only). */
export function UsersTab() {
  const { user: me, timezone } = useAuth();
  const [search, setSearch] = useState("");
  const [role, setRole] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const params = { search: search || undefined, role: role ?? undefined };
  const users = useUsers({ ...params, page, page_size: 20 });
  const { update, remove } = useUserMutations();
  const [editing, setEditing] = useState<UserOut | null | undefined>(undefined);
  const [deleting, setDeleting] = useState<UserOut | null>(null);

  const columns = useMemo<ColumnDef<UserOut>[]>(
    () => [
      {
        id: "name",
        header: "Name",
        meta: { exportValue: (u) => u.name },
        cell: ({ row }) => (
          <div>
            <p className="font-medium">{row.original.name}</p>
            <p className="text-muted-foreground text-xs">
              {row.original.username} · {row.original.email}
            </p>
          </div>
        ),
      },
      { id: "role", header: "Role", meta: { exportValue: (u) => u.role }, cell: ({ row }) => roleLabel[row.original.role] },
      {
        id: "signin",
        header: "Sign-in",
        meta: { exportValue: (u) => u.auth_provider },
        cell: ({ row }) => (row.original.auth_provider === "ldap" ? "Active Directory" : "Password"),
      },
      {
        id: "status",
        header: "Status",
        meta: { exportValue: (u) => (u.is_active ? "active" : "inactive") },
        cell: ({ row }) => (
          <div className="flex gap-1">
            <StatusBadge label={row.original.is_active ? "Active" : "Inactive"} tone={row.original.is_active ? "ok" : "neutral"} />
            {row.original.is_locked && <StatusBadge label="Locked" tone="bad" />}
          </div>
        ),
      },
      {
        id: "last_login",
        header: "Last sign-in",
        meta: { exportValue: (u) => u.last_login_at ?? "" },
        cell: ({ row }) => formatDateTime(row.original.last_login_at, timezone),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            {row.original.is_locked && (
              <Button
                variant="ghost"
                size="icon"
                className="size-8"
                aria-label={`Unlock ${row.original.name}`}
                onClick={() => update.mutate({ id: row.original.id, body: { unlock: true } }, { onError: showError })}
              >
                <LockOpen />
              </Button>
            )}
            <Button variant="ghost" size="icon" className="size-8" aria-label={`Edit ${row.original.name}`} onClick={() => setEditing(row.original)}>
              <Pencil />
            </Button>
            {row.original.id !== me?.id && (
              <Button variant="ghost" size="icon" className="size-8" aria-label={`Delete ${row.original.name}`} onClick={() => setDeleting(row.original)}>
                <Trash2 />
              </Button>
            )}
          </div>
        ),
      },
    ],
    [me?.id, timezone, update],
  );

  return (
    <>
      <DataTable
        columns={columns}
        rows={users.data?.data}
        total={users.data?.pagination.total ?? 0}
        page={page}
        pageSize={20}
        onPageChange={setPage}
        isLoading={users.isPending}
        error={users.error}
        onRetry={() => void users.refetch()}
        getRowId={(row) => String(row.id)}
        exportAll={() => fetchAllPages((p, page_size) => listUsers({ ...params, page: p, page_size }))}
        exportFileName="users.csv"
        toolbar={
          <>
            <SearchInput
              value={search}
              onChange={(value) => {
                setSearch(value);
                setPage(1);
              }}
              placeholder="Search name, username or email"
            />
            <FilterSelect
              label="Role"
              allLabel="All roles"
              value={role}
              options={(Object.keys(roleLabel) as UserRole[]).map((value) => ({ value, label: roleLabel[value] }))}
              onChange={(value) => {
                setRole(value);
                setPage(1);
              }}
            />
            <Button size="sm" onClick={() => setEditing(null)}>
              <UserPlus aria-hidden /> Add user
            </Button>
          </>
        }
        empty={<EmptyState icon={Users} title="No users match" description="Clear the filters or add a user." />}
      />
      <UserDialog user={editing ?? null} open={editing !== undefined} onClose={() => setEditing(undefined)} />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete ${deleting?.name ?? "user"}?`}
        description="The account is removed and signed out everywhere. Audit history keeps their name."
        confirmLabel="Delete user"
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
