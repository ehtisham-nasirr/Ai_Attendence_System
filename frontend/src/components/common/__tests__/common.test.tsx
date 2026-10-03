import type { ColumnDef } from "@tanstack/react-table";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";

describe("StatusBadge", () => {
  it("always shows the status as text, not colour alone", () => {
    render(<StatusBadge label="Late" tone="warn" />);
    expect(screen.getByText("Late")).toBeVisible();
  });
});

describe("ConfirmDialog", () => {
  it("blocks biometric erasure until the employee code is typed", async () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        open
        onOpenChange={vi.fn()}
        title="Erase all biometric data?"
        description="Permanent."
        confirmLabel="Erase permanently"
        requireText="E-041"
        onConfirm={onConfirm}
      />,
    );
    const button = screen.getByRole("button", { name: "Erase permanently" });
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/to confirm/), "E-04");
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/to confirm/), "1");
    await userEvent.click(button);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});

interface Row {
  id: number;
  name: string;
}

const columns: ColumnDef<Row>[] = [{ accessorKey: "name", header: "Name", meta: { sortKey: "name", exportValue: (r) => r.name } }];

describe("DataTable", () => {
  it("shows skeletons, then rows, and pages through results", async () => {
    const onPageChange = vi.fn();
    const props = {
      columns,
      total: 45,
      page: 1,
      pageSize: 20,
      onPageChange,
      empty: <p>Nothing here</p>,
    };
    const { rerender } = render(<DataTable {...props} rows={undefined} isLoading />);
    expect(screen.queryByText("Ayesha")).not.toBeInTheDocument();
    rerender(<DataTable {...props} rows={[{ id: 1, name: "Ayesha" }]} isLoading={false} />);
    expect(screen.getByText("Ayesha")).toBeInTheDocument();
    expect(screen.getByText("1–20 of 45")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("cycles server sort asc -> desc -> none", async () => {
    const onSortChange = vi.fn();
    const base = { columns, rows: [], total: 0, page: 1, pageSize: 20, onPageChange: vi.fn(), isLoading: false, empty: <p>Empty</p>, onSortChange };
    const { rerender } = render(<DataTable {...base} sort={null} />);
    await userEvent.click(screen.getByRole("button", { name: /Name/ }));
    expect(onSortChange).toHaveBeenLastCalledWith("name");
    rerender(<DataTable {...base} sort="name" />);
    await userEvent.click(screen.getByRole("button", { name: /Name/ }));
    expect(onSortChange).toHaveBeenLastCalledWith("-name");
    rerender(<DataTable {...base} sort="-name" />);
    await userEvent.click(screen.getByRole("button", { name: /Name/ }));
    expect(onSortChange).toHaveBeenLastCalledWith(null);
  });

  it("explains the next action when empty and shows errors with retry", async () => {
    const onRetry = vi.fn();
    const base = { columns, total: 0, page: 1, pageSize: 20, onPageChange: vi.fn(), isLoading: false };
    const { rerender } = render(<DataTable {...base} rows={[]} empty={<p>No cameras yet — Add your first camera</p>} />);
    expect(screen.getByText(/Add your first camera/)).toBeInTheDocument();
    rerender(<DataTable {...base} rows={[]} empty={<p />} error={new Error("Server down")} onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Server down");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalled();
  });
});
