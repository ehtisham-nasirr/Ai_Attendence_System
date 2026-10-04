import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type RowData,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown, Download } from "lucide-react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/common/ErrorState";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { downloadCsv, type CsvColumn } from "@/lib/csv";
import { cn } from "@/lib/utils";

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- generic names must match the library
  interface ColumnMeta<TData extends RowData, TValue> {
    /** Server sort key (`sort=key` / `sort=-key`); the column is sortable when set. */
    sortKey?: string;
    /** Value written to the CSV export; columns without it are not exported. */
    exportValue?: (row: TData) => string | number | boolean | null | undefined;
    className?: string;
  }
}

const PAGE_SIZES = [20, 50, 100, 200];

export interface DataTableProps<T> {
  columns: ColumnDef<T>[];
  rows: T[] | undefined;
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (pageSize: number) => void;
  sort?: string | null;
  onSortChange?: (sort: string | null) => void;
  isLoading: boolean;
  error?: unknown;
  onRetry?: () => void;
  /** Shown when the list is empty; explains the next action (§13). */
  empty: ReactNode;
  toolbar?: ReactNode;
  getRowId?: (row: T) => string;
  /** Loads every row that matches the current filters for the CSV export. */
  exportAll?: () => Promise<T[]>;
  exportFileName?: string;
  onRowClick?: (row: T) => void;
}

/** The one list table (standards/07): server-side paging and sort, search/filters, CSV export. */
export function DataTable<T>({
  columns,
  rows,
  total,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
  sort,
  onSortChange,
  isLoading,
  error,
  onRetry,
  empty,
  toolbar,
  getRowId,
  exportAll,
  exportFileName = "export.csv",
  onRowClick,
}: DataTableProps<T>) {
  const [exporting, setExporting] = useState(false);
  // eslint-disable-next-line react-hooks/incompatible-library -- TanStack Table returns unstable functions; this component is not compiler-optimised
  const table = useReactTable({
    data: rows ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    getRowId,
  });
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  const exportCsv = async () => {
    if (!exportAll) return;
    setExporting(true);
    try {
      const all = await exportAll();
      const csvColumns: CsvColumn<T>[] = table
        .getAllLeafColumns()
        .filter((column) => column.columnDef.meta?.exportValue)
        .map((column) => ({
          header: typeof column.columnDef.header === "string" ? column.columnDef.header : column.id,
          value: (row: T) => column.columnDef.meta?.exportValue?.(row),
        }));
      downloadCsv(exportFileName, csvColumns, all);
      toast.success(`Exported ${all.length} rows.`);
    } catch (exportError) {
      toast.error(exportError instanceof Error ? exportError.message : "Export failed.");
    } finally {
      setExporting(false);
    }
  };

  const toggleSort = (key: string) => {
    if (!onSortChange) return;
    if (sort === key) onSortChange(`-${key}`);
    else if (sort === `-${key}`) onSortChange(null);
    else onSortChange(key);
  };

  return (
    <div className="bg-card overflow-hidden rounded-lg border shadow-xs">
      {(toolbar || exportAll) && (
        <div className="flex flex-wrap items-center gap-2 border-b p-3">
          <div className="flex flex-1 flex-wrap items-center gap-2">{toolbar}</div>
          {exportAll && (
            <Button variant="outline" size="sm" onClick={() => void exportCsv()} disabled={exporting || total === 0}>
              <Download aria-hidden /> {exporting ? "Exporting…" : "Export CSV"}
            </Button>
          )}
        </div>
      )}
      {error ? (
        <ErrorState error={error} onRetry={onRetry} />
      ) : (
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((group) => (
              <TableRow key={group.id}>
                {group.headers.map((header) => {
                  const sortKey = header.column.columnDef.meta?.sortKey;
                  const direction = sort === sortKey ? "asc" : sort === `-${sortKey}` ? "desc" : null;
                  const label = header.isPlaceholder
                    ? null
                    : flexRender(header.column.columnDef.header, header.getContext());
                  return (
                    <TableHead
                      key={header.id}
                      className={header.column.columnDef.meta?.className}
                      aria-sort={direction === "asc" ? "ascending" : direction === "desc" ? "descending" : undefined}
                    >
                      {sortKey && onSortChange ? (
                        <button
                          type="button"
                          className="hover:text-foreground inline-flex items-center gap-1"
                          onClick={() => toggleSort(sortKey)}
                        >
                          {label}
                          {direction === "asc" ? (
                            <ArrowUp className="size-3.5" aria-hidden />
                          ) : direction === "desc" ? (
                            <ArrowDown className="size-3.5" aria-hidden />
                          ) : (
                            <ChevronsUpDown className="size-3.5 opacity-50" aria-hidden />
                          )}
                        </button>
                      ) : (
                        label
                      )}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 6 }, (_, index) => (
                <TableRow key={`skeleton-${index}`}>
                  {columns.map((_column, cellIndex) => (
                    <TableCell key={cellIndex}>
                      <Skeleton className="h-5 w-full max-w-40" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : table.getRowModel().rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="p-0">
                  {empty}
                </TableCell>
              </TableRow>
            ) : (
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  className={cn(onRowClick && "cursor-pointer")}
                  onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id} className={cell.column.columnDef.meta?.className}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      )}
      <div className="text-muted-foreground flex flex-wrap items-center justify-between gap-3 border-t px-3 py-2 text-sm">
        <span>
          {total === 0 ? "No results" : `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} of ${total}`}
        </span>
        <div className="flex items-center gap-2">
          {onPageSizeChange && (
            <Select value={String(pageSize)} onValueChange={(value) => onPageSizeChange(Number(value))}>
              <SelectTrigger size="sm" aria-label="Rows per page" className="w-20">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZES.map((size) => (
                  <SelectItem key={size} value={String(size)}>
                    {size}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <Button
            variant="outline"
            size="icon"
            className="size-8"
            aria-label="Previous page"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
          >
            <ChevronLeft />
          </Button>
          <span className="tabular-nums">
            {page} / {pageCount}
          </span>
          <Button
            variant="outline"
            size="icon"
            className="size-8"
            aria-label="Next page"
            disabled={page >= pageCount}
            onClick={() => onPageChange(page + 1)}
          >
            <ChevronRight />
          </Button>
        </div>
      </div>
    </div>
  );
}
